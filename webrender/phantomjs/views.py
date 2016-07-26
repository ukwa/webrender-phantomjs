import os
import re
import sys
import json
import base64
import random
import signal
import logging
from datetime import date
from PIL import Image
from functools import wraps
from phantomjs.settings import *
from subprocess import Popen, PIPE
from django.views.decorators.gzip import gzip_page
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseServerError

handler = logging.StreamHandler()

logger = logging.getLogger("phantomjs.views")
#logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Add warc-prefix is json in Warcprox-Meta: header


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

def get_image(request, url):
    """Tries to render an image of a URL, returning a 500 if it times out."""
    data = generate_image(url)
    return HttpResponse(content=data, content_type="image/png")

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

def get_har_with_image(url, selectors=None):
    """Gets the raw HAR output from PhantomJs with rendered image(s)."""
    tmp = "%s/%s.json" % (temp, str(random.randint(0, 100000000)))
    command = phantomjs_cmd() + [domimage, url, tmp]
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
        output = i.read()
    os.remove(tmp)
    return output

def get_raw(request, url):
    """Tries to retrieve the HAR, returning a 500 if timing out."""
    js = get_har(url)
    return HttpResponse(content=js, content_type="application/json")

def generate_urls(url):
    """Tries to retrieve a list of URLs from the HAR."""
    js = get_har(url)

    data = json.loads(js)
    return "\n".join([entry["request"]["url"] for entry in data["log"]["entries"]])

def get_urls(request, url):
    """Tries to retrieve a list of URLs, returning a 500 if timing out."""
    response = generate_urls(url)
    return HttpResponse(content=response, content_type="text/plain")

@gzip_page
def get_image_and_urls(request, url):
    """Deprecated in lieu of the HAR-based 'get_dom_image'."""
    image = base64.b64encode(generate_image(url))
    urls = generate_urls(url)
    data = [{'image':image, 'urls':urls}]
    json_string = json.dumps(data)
    return HttpResponse(content=json_string, content_type="application/json")

@gzip_page
@csrf_exempt
def get_dom_image(request, url):
    """
    Tries to retrieve the HAR with rendered images, returning a 500 if timing out.
    If data is POST'd it expects a string-representation of a list of selectors, e.g.:
    "[\":root\"]"
    """
    if request.method == "POST" and request.body:
        selectors = json.loads(request.body.decode("utf-8"))
        har = get_har_with_image(url, selectors)
    else:
        har = get_har_with_image(url)
    if har.startswith("FAIL"):
        return HttpResponseServerError(content="%s" % har, content_type="text/plain")
    return HttpResponse(content=har, content_type="application/json")

