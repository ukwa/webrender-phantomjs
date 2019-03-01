import os
import io
import json
import base64
import shutil
import tempfile
import logging as logger
import urllib.request
import urllib.error
from PIL import Image
from datetime import date
import docker
client = docker.from_env()


# Location of WARCPROX proxy used to store WARC records:
WARCPROX = os.getenv("WARCPROX", None)


def get_har_with_image(url, selectors=None, proxy=WARCPROX, warc_prefix=date.today().isoformat(),
                       include_rendered=False, return_screenshot=False):
    """Gets the raw HAR output from PhantomJs with rendered image(s)."""

    # Set up Docker container environment:
    if not proxy and 'HTTP_PROXY' in os.environ:
        proxy = os.environ['HTTP_PROXY']
    d_env = {
        'HTTP_PROXY': proxy,
        'HTTPS_PROXY': proxy
    }

    # Set up volume mount:
    tmp_dir = tempfile.mkdtemp(dir=os.environ.get('WEB_RENDER_TMP', '/tmp/'))
    d_vol = {
        tmp_dir: {'bind': '/output', 'mode': 'rw'}
    }
    # Set up the container and run it:
    d_c = client.containers.create('ukwa/webrender-puppeteer', command="node renderer.js %s" % url,
                                   environment=d_env, volumes=d_vol, cap_add=['SYS_ADMIN'],
                                   detach=True, restart_policy={"Name": "on-failure", "MaximumRetryCount": 2})
    d_c.start()
    d_c.wait(timeout=60*7) # Kill renders that take far too long (7 mins)
    #d_c.wait(timeout=10) # Short-time out for debugging.
    d_logs = d_c.logs()
    d_c.stop()
    d_c.remove(force=True)

    # If this fails completely, assume this was a temporary problem and suggest retrying the request:
    tmp = os.path.join(tmp_dir,'./rendered.har')
    if not os.path.exists(tmp):
        logger.error("Rendering to JSON failed for %s" % url)
        logger.warning("FAILED:\logs=%s" % d_logs )
        return "FAIL"
    else:
        logger.debug("GOT:\nlogs=%s" % d_logs)
    with open(tmp, "r") as i:
        har = i.read()
    shutil.rmtree(tmp_dir)
    output = _warcprox_write_har_content(har, url, warc_prefix, warcprox=proxy,
                                         include_rendered_in_har=include_rendered, return_screenshot=return_screenshot)
    return output

def full_and_thumb_jpegs(large_png):
    # Load the image and drop the alpha channel:
    img = Image.open(io.BytesIO(large_png))
    img = remove_transparency(img)
    img = img.convert("RGB")
    # Save it as a JPEG:
    out = io.BytesIO()
    img.save(out, "jpeg", quality=95)
    full_jpeg = out.getvalue()

    w, h = img.size
    logger.debug("Types are %s, %s" % ( type(w), type(h) ))
    h = int(h)
    logger.debug("IMAGE %i x %x" % (w,h))
    thumb_width = 300
    thumb_height = int((float(thumb_width) / w) * h)
    logger.debug("Got %i x %x" % (thumb_width,thumb_height))
    img.thumbnail((thumb_width, thumb_height))
    
    out = io.BytesIO()
    img.save(out, "jpeg", quality=95)
    thumb_jpeg = out.getvalue()

    return full_jpeg, thumb_jpeg

def remove_transparency(im, bg_colour=(255, 255, 255)):

    # Only process if image has transparency (http://stackoverflow.com/a/1963146)
    if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):

        # Need to convert to RGBA if LA format due to a bug in PIL (http://stackoverflow.com/a/1963146)
        alpha = im.convert('RGBA').split()[-1]

        # Create a new background image of our matt color.
        # Must be RGBA because paste requires both images have the same format
        # (http://stackoverflow.com/a/8720632  and  http://stackoverflow.com/a/9459208)
        bg = Image.new("RGBA", im.size, bg_colour + (255,))
        bg.paste(im, mask=alpha)
        return bg

    else:
        return im

# HTML5: https://dev.w3.org/html5/spec-preview/image-maps.html
# <img src="shapes.png" usemap="#shapes"
#      alt="Four shapes are available: a red hollow box, a green circle, a blue triangle, and a yellow four-pointed star.">
# <map name="shapes">
#  <area shape=rect coords="50,50,100,100"> <!-- the hole in the red box -->
#  <area shape=rect coords="25,25,125,125" href="red.html" alt="Red box.">
#  <area shape=circle coords="200,75,50" href="green.html" alt="Green circle.">
#  <area shape=poly coords="325,25,262,125,388,125" href="blue.html" alt="Blue triangle.">
#  <area shape=poly coords="450,25,435,60,400,75,435,90,450,125,465,90,500,75,465,60"
#        href="yellow.html" alt="Yellow star.">
# </map>
# <img alt="Embedded Image" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIA..." />
def build_imagemap(page_jpeg, page):
    html = "<html><head><title>%s [Static version of %s]</title>\n</head>\n<body style=\"margin: 0;\">\n" % (page['title'], page['url'])
    html = html + '<img src="data:image/jpeg;base64,%s" usemap="#shapes" alt="%s">\n' %( base64.b64encode(page_jpeg).decode('utf-8'), page['title'])
    html = html + '<map name="shapes">\n'
    for box in page['map']:
        if 'href' in box:
            x1 = box['location']['left']
            y1 = box['location']['top']
            x2 = x1 + box['location']['width']
            y2 = y1 + box['location']['height']
            html = html + '<area shape=rect coords="%i,%i,%i,%i" href="%s">\n' % (x1,y1,x2,y2,box['href'])
        else:
            logger.debug("Skipping box with no 'href': %s" % box)
    html = html + '</map>\n'
    html = html + "</body>\n</html>\n"
    return html


# We use the page ID (i.e. the original URL) to identify records, but note that the final URL can be different.
def _warcprox_write_har_content(har_js, url, warc_prefix, warcprox=WARCPROX, include_rendered_in_har=False,
                                return_screenshot=False):
    warcprox_headers = { "Warcprox-Meta" : json.dumps( { 'warc-prefix' : warc_prefix}) }
    har = json.loads(har_js)
    # If there are no entries, something went very wrong:
    if len(har['log']['entries']) == 0:
        logger.error("No entries in log: " + har_js)
        raise Exception("No requests/responses logged! Rendering failed!")
    # Look at page contents:
    for page in har['log']['pages']:
        dom = page['renderedContent']['text']
        dom = base64.b64decode(dom)

        # Store the page URL, which can be different (redirects etc.)
        location = page.get('url', None)

        # Store the on-ready DOM:
        _warcprox_write_record(warcprox_address=warcprox,
                url="onreadydom:{}".format(page.get('id',None)),
                warc_type="resource", content_type="text/html",
                payload=dom, location=location,
                extra_headers= warcprox_headers )
        # Store the rendered elements:
        full_png = None
        for rende in page['renderedElements']:
            selector = rende['selector']
            im_fmt = rende['format']
            if im_fmt == 'PNG':
                im_fmt = 'image/png'
            elif im_fmt == 'JPEG' or im_fmt == 'JPG':
                im_fmt = 'image/jpeg'
            else:
                im_fmt = 'application/octet-stream; ext=%s' % im_fmt
            content = rende['content']
            image = base64.b64decode(content)
            # Keep the :root image
            if selector == ':root':
                full_png = image
                xpointurl = page.get('id')
            else:
                # https://www.w3.org/TR/2003/REC-xptr-framework-20030325/
                xpointurl = "%s#xpointer(%s)" % (page.get('id'), selector)
            # And write the WARC:
            _warcprox_write_record(warcprox_address=warcprox,
                url="screenshot:{}".format(xpointurl),
                warc_type="resource", content_type=im_fmt,
                payload=image, location=location,
                extra_headers=warcprox_headers)
        # If we have a full-page PNG:
        if full_png:
            # Store a thumbnail:
            (full_jpeg, thumb_jpeg) = full_and_thumb_jpegs(full_png)
            _warcprox_write_record(warcprox_address=warcprox,
                url="thumbnail:{}".format(page['id']),
                warc_type="resource", content_type='image/jpeg',
                payload=thumb_jpeg, location=location, extra_headers=warcprox_headers)
            # Store an image map HTML file:
            imagemap = build_imagemap(full_jpeg, page)
            _warcprox_write_record(warcprox_address=warcprox,
                url="imagemap:{}".format(page['id']),
                warc_type="resource", content_type='text/html; charset="utf-8"',
                payload=bytearray(imagemap,'UTF-8'), location=location,
                extra_headers=warcprox_headers)
            if return_screenshot:
                return full_png

        # And remove rendered forms from HAR:
        if not include_rendered_in_har:
            del page['renderedElements']
            del page['renderedContent']

    # Store the HAR
    _warcprox_write_record(warcprox_address=warcprox,
                           url="har:{}".format(url),
                           warc_type="resource", content_type="application/json",
                           payload=bytearray(json.dumps(har), "UTF-8"),
                           extra_headers=warcprox_headers)

    return har


def _warcprox_write_record(
        warcprox_address, url, warc_type, content_type,
        payload, location=None, extra_headers=None):
    headers = {"Content-Type": content_type, "WARC-Type": warc_type, "Host": "N/A"}
    if location:
        headers['Location'] = location
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, method="WARCPROX_WRITE_RECORD",
                                     headers=headers, data=payload)

    # XXX setting request.type="http" is a hack to stop urllib from trying
    # to tunnel if url is https
    request.type = "http"
    if warcprox_address:
        request.set_proxy(warcprox_address, "http")
        logger.debug("Connecting via "+warcprox_address)
    else:
        logger.error("Cannot write WARC records without warcprox!")
        return

    try:
        with urllib.request.urlopen(request) as response:
            if response.status != 204:
                logger.warning(
                    'got "%s %s" response on warcprox '
                    'WARCPROX_WRITE_RECORD request (expected 204)',
                    response.status, response.reason)
    except urllib.error.HTTPError as e:
        logger.warning(
            'got "%s %s" response on warcprox '
            'WARCPROX_WRITE_RECORD request (expected 204)',
            e.getcode(), e.info())

