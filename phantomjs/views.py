import os
import re
import json
import base64
import random
import signal
import logging
from PIL import Image
from functools import wraps
from phantomjs.settings import *
from subprocess import Popen, PIPE
from django.views.decorators.gzip import gzip_page
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseServerError

logger = logging.getLogger("phantomjs.views")

def generate_image(url):
    """Returns a 1280x960 rendering of the webpage."""
    tmp = "%s/%s.jpg" % (temp, str(random.randint(0, 100)))
    image = Popen([phantomjs, rasterize, url, tmp], stdout=PIPE, stderr=PIPE)
    stdout, stderr = image.communicate()
    im = Image.open(tmp)
    crop = im.crop((0, 0, 1280, 960))
    crop.save(tmp, "JPEG")
    data = open(tmp, "rb").read()
    os.remove(tmp)
    return data

def get_image(request, url):
    """Tries to render an image of a URL, returning a 500 if it times out."""
    data = generate_image(url)
    return HttpResponse(content=data, content_type="image/jpeg")

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
    har = Popen([phantomjs, netsniff, url], stdout=PIPE, stderr=PIPE)
    stdout, stderr = har.communicate()
    return strip_debug(stdout)

def get_har_with_image(url, selectors=None):
    """Gets the raw HAR output from PhantomJs with rendered image(s)."""
    tmp = "%s/%s.json" % (temp, str(random.randint(0, 100)))
    command = [phantomjs, domimage, url, tmp]
    if selectors is not None:
        command += selectors
    har = Popen(command, stdout=PIPE, stderr=PIPE)
    stdout, stderr = har.communicate()
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
    """Tries to retrieve the HAR with rendered images, returning a 500 if timing out."""
    if request.method == "POST" and request.body:
        selectors = json.loads(request.body.decode("utf-8"))
        har = get_har_with_image(url, selectors)
    else:
        har = get_har_with_image(url)
    if har.startswith("FAIL"):
        return HttpResponseServerError(content="%s" % har, content_type="text/plain")
    return HttpResponse(content=har, content_type="application/json")

