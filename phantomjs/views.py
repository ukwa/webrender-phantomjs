import os
import re
import base64
import random
import signal
import logging
import simplejson
from PIL import Image
from phantomjs.settings import *
from subprocess import Popen, PIPE
from django.views.decorators.gzip import gzip_page
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseServerError

logger = logging.getLogger( "phantomjs.views" )

class TimeoutException( Exception ):
	"""Thrown when timeout limit exceeded."""
	def __init__( self, message ):
		Exception.__init__( self, message )

def timeout( limit ):
	"""Decorator specifying a timeout limit."""
	def decorate( f ):
		def handler( signum, frame ):
			raise TimeoutException( "Timed out." )

		def new_f( *args, **kwargs ):
			old_handler = signal.signal( signal.SIGALRM, handler )
			signal.alarm( limit )
			result = f( *args, **kwargs )
			signal.signal( signal.SIGALRM, old_handler )
			signal.alarm( 0 )
			return result

		new_f.func_name = f.func_name
		return new_f
	return decorate

@timeout( timeout_limit )
def generate_image( url ):
	"""Returns a 1280x960 rendering of the webpage."""
	tmp = temp + str( random.randint( 0, 100 ) ) + ".jpg"
	image = Popen( [ phantomjs, rasterize, url, tmp ], stdout=PIPE, stderr=PIPE )
	stdout, stderr = image.communicate()
	im = Image.open( tmp )
	crop = im.crop( ( 0, 0, 1280, 960 ) )
	crop.save( tmp, "JPEG" )
	data = open( tmp, "rb" ).read()
	os.remove( tmp )
	return data

def get_image( request, url ):
	"""Tries to render an image of a URL, returning a 500 if it times out."""
	try:
		data = generate_image( url )
	except TimeoutException as t:
		return HttpResponseServerError( content=str( t ) )
	return HttpResponse( content=data, mimetype="image/jpeg" )

def strip_debug( json ):
	"""PhantomJs seems to merge its output with its error messages; this
	tries to strip them."""
	lines = json.splitlines()
	for index, line in enumerate( lines ):
		if line.startswith( "{" ):
			return "\n".join( lines[ index: ] )
	return json

@timeout( timeout_limit )
def get_har( url ):
	"""Gets the raw HAR output from PhantomJs."""
	har = Popen( [ phantomjs, netsniff, url ], stdout=PIPE, stderr=PIPE )
	stdout, stderr = har.communicate()
	return strip_debug( stdout )

@timeout( timeout_limit )
def get_har_with_image( url, selectors=None ):
	"""Gets the raw HAR output from PhantomJs with rendered image(s)."""
	command = [ phantomjs, domimage, url ]
	if selectors is not None:
		command += selectors
	har = Popen( command, stdout=PIPE, stderr=PIPE )
	stdout, stderr = har.communicate()
	return strip_debug( stdout )

def get_raw( request, url ):
	"""Tries to retrieve the HAR, returning a 500 if timing out."""
	try:
		json = get_har( url )
	except TimeoutException as t:
		return HttpResponseServerError( content=str( t ) )
	return HttpResponse( content=json, mimetype="application/json" )

def generate_urls( url ):
	"""Tries to retrieve a list of URLs from the HAR."""
	json = get_har( url )

	data = simplejson.loads( json )
	return "\n".join( [ entry[ "request" ][ "url" ] for entry in data[ "log" ][ "entries" ] ] )

def get_urls( request, url ):
	"""Tries to retrieve a list of URLs, returning a 500 if timing out."""
	try:
		response = generate_urls( url )
	except TimeoutException as t:
		return HttpResponseServerError( content=str( t ) )
	return HttpResponse( content=response, mimetype="text/plain" )

@gzip_page
def get_image_and_urls( request, url ):
	"""Deprecated in lieu of the HAR-based 'get_dom_image'."""
	try:
		image = base64.b64encode( generate_image( url ) )
		urls = generate_urls( url )
	except TimeoutException as t:
		return HttpResponseServerError( content=str( t ) )
	data = [ { 'image':image, 'urls':urls } ]
	json_string = simplejson.dumps( data )
	return HttpResponse( content=json_string, mimetype="application/json" )

@gzip_page
@csrf_exempt
def get_dom_image( request, url ):
	"""Tries to retrieve the HAR with rendered images, returning a 500 if timing out."""
	try:
		if request.method == "POST":
			selectors = request.POST.values()
			har = get_har_with_image( url, selectors )
		else:
			har = get_har_with_image( url )
	except TimeoutException as t:
		return HttpResponseServerError( content=str( t ) )
	if har.startswith( "FAIL" ):
		return HttpResponseServerError( content="%s" % har, mimetype="text/plain" )
	return HttpResponse( content=har, mimetype="application/json" )

