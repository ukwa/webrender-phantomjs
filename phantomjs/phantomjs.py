import os
import io
import json
import base64
import tempfile
import logging as logger
import urllib.request
import urllib.error
from PIL import Image
from subprocess import Popen, PIPE
from datetime import date


# Location of the PhantomJS binary:
PHANTOMJS_BINARY = os.getenv('PHANTOMJS_BINARY', "phantomjs")

# Location of the PhantomJS script we need:
PHANTOMJS_RENDER_SCRIPT = os.getenv('PHANTOMJS_RENDER_SCRIPT', "phantomjs/phantomjs-render.js")

# Location of WARCPROX proxy used to store WARC records:
WARCPROX = os.getenv("WARCPROX", None)

# --proxy=XXX.XXX:9090
def phantomjs_cmd(proxy=None):
    cmd = [PHANTOMJS_BINARY, "--ssl-protocol=any", "--ignore-ssl-errors=true", "--web-security=false"]
    if not proxy and 'HTTP_PROXY' in os.environ:
        proxy = os.environ['HTTP_PROXY']
    if proxy:
        logger.debug("Using proxy: %s" % proxy)
        cmd = cmd + [ "--proxy=%s" % proxy ]
    return cmd

def popen_with_env(clargs, warc_prefix=None):
    # Set up a copy of the environment variables, with one for the WARC prefix:
    sub_env = dict(os.environ, WARCPROX_WARC_PREFIX=warc_prefix,
                   USER_AGENT_ADDITIONAL="bl.uk_lddc_renderbot/2.0.0 (+ http://www.bl.uk/aboutus/legaldeposit/websites/websites/faqswebmaster/index.html)")
    logger.debug("Using WARCPROX_WARC_PREFIX=%s" % sub_env['WARCPROX_WARC_PREFIX'])
    # And open the process:
    return Popen(clargs, stdout=PIPE, stderr=PIPE, env=sub_env)

def strip_debug(js):
    """PhantomJs seems to merge its output with its error messages; this
    tries to strip them."""
    lines = js.decode("utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("{"):
            return "\n".join(lines[index:])
    return js

def get_har_with_image(url, selectors=None, warcprox=WARCPROX, warc_prefix=date.today().isoformat(),
                       include_rendered=False, return_screenshot=False):
    """Gets the raw HAR output from PhantomJs with rendered image(s)."""
    (fd, tmp) = tempfile.mkstemp()
    command = phantomjs_cmd(warcprox) + [PHANTOMJS_RENDER_SCRIPT, url, tmp]
    if selectors:
        command = command + selectors.split(" ")
    logger.debug("Using command: %s " % " ".join(command))
    har = popen_with_env(command, warc_prefix=warc_prefix)
    stdout, stderr = har.communicate(timeout=60*10) # Kill renders that take far too long (10 mins)
    # If this fails completely, assume this was a temporary problem and suggest retrying the request:
    if not os.path.exists(tmp):
        logger.error("Rendering to JSON failed for %s" % url)
        logger.warning("FAILED:\nstdout=%s\nstderr=%s" % (stdout, stderr) )
        return "FAIL"
        #return '{ "failed": true, "retry": true }'
    else:
        logger.debug("GOT:\nstdout=%s\nstderr=%s" % (stdout, stderr))
    with open(tmp, "r") as i:
        har = i.read()
    os.remove(tmp)
    output = _warcprox_write_har_content(har, url, warc_prefix, warcprox=warcprox,
                                         include_rendered_in_har=include_rendered, return_screenshot=return_screenshot)
    return output

def full_and_thumb_jpegs(large_png):
    img = Image.open(io.BytesIO(large_png))
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
        # Store the on-ready DOM:
        _warcprox_write_record(warcprox_address=warcprox,
                url="onreadydom:{}".format(page.get('url',None)),
                warc_type="resource", content_type="text/html",
                payload=dom,
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
                xpointurl = page.get('url')
            else:
                # https://www.w3.org/TR/2003/REC-xptr-framework-20030325/
                xpointurl = "%s#xpointer(%s)" % (page.get('url'), selector)
            # And write the WARC:
            _warcprox_write_record(warcprox_address=warcprox,
                url="screenshot:{}".format(xpointurl),
                warc_type="resource", content_type=im_fmt,
                payload=image,
                extra_headers=warcprox_headers)
        # If we have a full-page PNG:
        if full_png:
            # Store a thumbnail:
            (full_jpeg, thumb_jpeg) = full_and_thumb_jpegs(full_png)
            _warcprox_write_record(warcprox_address=warcprox,
                url="thumbnail:{}".format(page['url']),
                warc_type="resource", content_type='image/jpeg',
                payload=thumb_jpeg, extra_headers=warcprox_headers)
            # Store an image map HTML file:
            imagemap = build_imagemap(full_jpeg, page)
            _warcprox_write_record(warcprox_address=warcprox,
                url="imagemap:{}".format(page['url']),
                warc_type="resource", content_type='text/html; charset="utf-8"',
                payload=bytearray(imagemap,'UTF-8'),
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
        payload, extra_headers=None):
    headers = {"Content-Type": content_type, "WARC-Type": warc_type, "Host": "N/A"}
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

