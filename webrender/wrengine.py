from webrender.puppeteer.docker import get_har_with_image
import logging
import io
import flask

# Flash application context
app = flask.Flask(__name__)

# Setup logging
logging.getLogger().setLevel(logging.INFO)

@app.route('/')
def welcome():
    """
    :return: The Wrender homepage
    """
    return 'Wrender'


@app.route('/ping')
def ping():
    """
    :return: a simple message to verify the system is running.
    """
    return 'pong'


@app.route('/render')
def render():
    """
    Tries to retrieve the HAR with rendered images, returning a 500 if timing out.
    If data is POST'd it expects a string-representation of a list of selectors, e.g.:
    "[\":root\"]"
    """
    url = flask.request.args.get('url')
    app.logger.info("Got URL: %s" % url)
    #
    selectors = flask.request.args.get('selectors', ':root')
    app.logger.debug("Got selectors: %s" % selectors)
    #
    warc_prefix = flask.request.args.get('warc_prefix', 'wrender')
    app.logger.debug("Got WARC prefix: %s" % warc_prefix)
    #
    include_rendered = flask.request.args.get('include_rendered', False)
    app.logger.debug("Got include_rendered: %s" % include_rendered)
    #
    show_screenshot = flask.request.args.get('show_screenshot', False)
    app.logger.debug("Got show_screenshot: %s" % show_screenshot)
    #
    if show_screenshot:
        return flask.send_file(io.BytesIO(
            get_har_with_image(url, selectors, warc_prefix=warc_prefix,
                  include_rendered=include_rendered, return_screenshot=True)), mimetype='image/png')
    else:
        return flask.jsonify(get_har_with_image(url, selectors, warc_prefix=warc_prefix,
                                                          include_rendered=include_rendered))
