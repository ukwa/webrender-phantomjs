import logging
import json
from flask import Flask, request, jsonify
app = Flask(__name__)

from phantomjs.phantomjs import get_har_with_image

logging.getLogger().setLevel(logging.DEBUG)

@app.route('/')
def hello_world():
    return 'Hello, World!'


@app.route('/render')
def render():
    """
    Tries to retrieve the HAR with rendered images, returning a 500 if timing out.
    If data is POST'd it expects a string-representation of a list of selectors, e.g.:
    "[\":root\"]"
    """
    url = request.args.get('url')
    app.logger.debug("Got URL: %s" % url)
    json_selectors = request.args.get('selectors')
    if json_selectors:
        selectors = json.loads(json_selectors)
    else:
        selectors = None
    app.logger.debug("Got selectors: %s" % selectors)
    #return Response(get_har_with_image(url,selectors), mimetype='application/json')
    return jsonify(get_har_with_image(url,selectors))
