import os
import re
import io
import sys
import json
import uuid
import base64
import random
import signal
import logging as logger
import urllib.request
from functools import wraps
from PIL import Image
from subprocess import Popen, PIPE
from datetime import date

root = "/phantomjs"
phantomjs = "%s/bin/phantomjs" % root
phantomjs = "phantomjs"
rasterize = "/django-phantomjs/examples/rasterize.js"
netsniff = "%s/examples/netsniff.js" % root
domimage = "phantomjs/phantomjs-render.js"
temp = "/var/tmp"
timeout_limit = 30
crop_rasterize_image = False
owb_proxy="openwayback:8090"


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
    request.set_proxy(warcprox_address, "http")
    logger.info("Connecting via "+warcprox_address)

    try:
        with urllib.request.urlopen(request) as response:
            if response.status != 204:
                logger.warn(
                    'got "%s %s" response on warcprox '
                    'WARCPROX_WRITE_RECORD request (expected 204)',
                    response.status, response.reason)
    except urllib.error.HTTPError as e:
        logger.warn(
            'got "%s %s" response on warcprox '
            'WARCPROX_WRITE_RECORD request (expected 204)',
            e.getcode(), e.info())


# --proxy=XXX.XXX:9090
def phantomjs_cmd(proxy=None):
    cmd = [phantomjs, "--ssl-protocol=any"]
    if not proxy and 'HTTP_PROXY' in os.environ:
        proxy = os.environ['HTTP_PROXY']
    if proxy:
        logger.debug("Using proxy: %s" % proxy)
        cmd = cmd + [ "--proxy=%s" % proxy ]
    return cmd

def popen_with_env(clargs):
    # Set up a copy of the environment variables, with one for the WARC prefix:
    sub_env = dict(os.environ, WARCPROX_WARC_PREFIX=date.today().isoformat())
    logger.debug("Using WARCPROX_WARC_PREFIX=%s" % sub_env['WARCPROX_WARC_PREFIX'])
    # And open the process:
    return Popen(clargs, stdout=PIPE, stderr=PIPE, env=sub_env)

def generate_image(url, proxy=None):
    """Returns a 1280x960 rendering of the webpage."""
    logger.debug("Rendering: %s..." %url)
    tmp = "%s/%s.png" % (temp, str(random.randint(0, 100000000)))
    cmd = phantomjs_cmd(proxy) + [rasterize, url, tmp, "1280px"]
    logger.debug("Using command: %s " % " ".join(cmd))
    image = popen_with_env(cmd)
    stdout, stderr = image.communicate()
    if stdout:
        logger.debug("phantomjs.info: %s" % stdout)
    if stderr:
        logger.debug("phantomjs.error: %s" % stderr)
    if crop_rasterize_image:
        im = Image.open(tmp)
        crop = im.crop((0, 0, 1280, 1024))
        crop.save(tmp, format='PNG')
        logger.debug("Cropped.")
    data = open(tmp, "rb").read()
    os.remove(tmp)
    return data

def strip_debug(js):
    """PhantomJs seems to merge its output with its error messages; this
    tries to strip them."""
    lines = js.decode("utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("{"):
            return "\n".join(lines[index:])
    return js

def get_har(url):
    """Gets the raw HAR output from PhantomJs."""
    har = popen_with_env(phantomjs_cmd() + [netsniff, url])
    stdout, stderr = har.communicate()
    return strip_debug(stdout)

def get_har_with_image(url, selectors=None, warcprox="localhost:8000"):
    """Gets the raw HAR output from PhantomJs with rendered image(s)."""
    tmp = "%s/%s.json" % (temp, uuid.uuid4())
    command = phantomjs_cmd(warcprox) + [domimage, url, tmp]
    logger.debug("Using command: %s " % " ".join(command))
    if selectors is not None:
        command += selectors
    har = popen_with_env(command)
    stdout, stderr = har.communicate()
    # If this fails completely, assume this was a temporary problem and suggest retrying the request:
    if not os.path.exists(tmp):
        logger.error("Rendering to JSON failed for %s" % url)
        logger.info("FAILED:\nstdout=%s\nstderr=%s" % (stdout, stderr) )
        return "FAIL"
        #return '{ "failed": true, "retry": true }'
    with open(tmp, "r") as i:
        har = i.read()
    os.remove(tmp)
    har = _warcprox_write_har_content(har, warcprox)
    return har

def generate_urls(url):
    """Tries to retrieve a list of URLs from the HAR."""
    js = get_har(url)

    data = json.loads(js)
    return "\n".join([entry["request"]["url"] for entry in data["log"]["entries"]])

def full_and_thumb_jpegs(large_png):
    img = Image.open(io.BytesIO(large_png))
    out = io.BytesIO()
    img.save(out, "jpeg", quality=95)
    full_jpeg = out.getvalue()

    w, h = img.size
    logger.info("Types are %s, %s" % ( type(w), type(h) ))
    h = int(h)
    logger.info("IMAGE %i x %x" % (w,h))
    thumb_width = 300
    thumb_height = int((float(thumb_width) / w) * h)
    logger.info("Got %i x %x" % (thumb_width,thumb_height))
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
    html = "<html><head><title>%s - Static version of %s</title>\n</head>\n<body>\n" % (page['title'], page['url'])
    html = html + '<img src="data:image/jpeg;base64,%s" usemap="#shapes" alt="%s">\n' %( base64.b64encode(page_jpeg), page['title'])
    html = html + '<map name="shapes">\n'
    for box in page['map']:
        x1 = box['location']['left']
        y1 = box['location']['top']
        x2 = x1 + box['location']['width']
        y2 = y1 + box['location']['height']
        html = html + '<area shape=rect coords="%i,%i,%i,%i" href="%s">\n' % (x1,y1,x2,y2,box['href'])
    html = html + '</map>\n'
    html = html + "</body>\n</html>\n"
    return html


def _warcprox_write_har_content(har_js, warcprox=None, include_render_in_har=False):
    if not warcprox:
        warcprox = os.environ['HTTP_PROXY']
    warcprox_headers = { "Warcprox-Meta" : json.dumps( { 'warc-prefix' : 'Wrender'}) }
    har = json.loads(har_js)
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
            # https://www.w3.org/TR/2003/REC-xptr-framework-20030325/
            if selector == ":root":
                xpointurl = page.get('url')
            else:
                xpointurl = "%s#xpointer(%s)" % (page.get('url'), selector)
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
        # And remove rendered forms from HAR:
        if not include_render_in_har:
            page['renderedElements'] = None
            page['renderedContent'] = None

    # Store the HAR
    _warcprox_write_record(warcprox_address=warcprox,
                           url="har:{}".format(page.get('url', None)),
                           warc_type="resource", content_type="application/json",
                           payload=bytearray(json.dumps(har), "UTF-8"),
                           extra_headers=warcprox_headers)

    return har
