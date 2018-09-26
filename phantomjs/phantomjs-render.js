/**
 * Largely a combination of PhantomJs' default 'rasterize' and 'netsniff'
 * scripts. This adds the potential for including 'renderedElements', i.e.
 * images of particular elements within a page, in the output.
 *
 * This breaks the HAR spec. as it currently stands.
 *
 * Asynchronous rendering borrowed from:
 * https://gist.github.com/cjoudrey/1341747
 */

if (!Date.prototype.toISOString) {
    Date.prototype.toISOString = function () {
        function pad(n) { return n < 10 ? '0' + n : n; }
        function ms(n) { return n < 10 ? '00'+ n : n < 100 ? '0' + n : n }
        return this.getFullYear() + '-' +
            pad(this.getMonth() + 1) + '-' +
            pad(this.getDate()) + 'T' +
            pad(this.getHours()) + ':' +
            pad(this.getMinutes()) + ':' +
            pad(this.getSeconds()) + '.' +
            ms(this.getMilliseconds()) + 'Z';
    }
}

capture = function(clipRect) {
    if (clipRect) {
         if (!typeof(clipRect) === "object") {
            throw new Error("clipRect must be an Object instance.");
        }
        if( clipRect.height < 50 ) {
            console.log("WARNING: Very small (clipRect.height = " + clipRect.height + ") using page.viewportSize.height...");
            clipRect.height = page.viewportSize.height;
        }
        // Many tools struggle with PNG images taller than 31500 pixels:
        if( clipRect.height > 31500 ) {
            console.log("WARNING: Very tall clip (clipRect.height = " + clipRect.height + ") resetting to 31500...");
            clipRect.height = 31500;
        }
    }
    try {
        page.clipRect = clipRect;
        console.log("INFO: Rendering to clipped region... "+page.clipRect.top+", "+page.clipRect.left+": "+page.clipRect.width+" x "+page.clipRect.height);
        //page.render("pjs-test.png");
        return page.renderBase64('PNG');
    } catch (e) {
        console.log("ERROR: Failed to capture screenshot: " + e, "error");
    }
}

captureSelector = function(selector) {
    var clipRect = page.evaluate(function(selector) {
        var e = document.querySelector(selector);
        if(e != null) {
            return document.querySelector(selector).getBoundingClientRect();
        }
    }, selector);
    if(clipRect != null) {
        return capture(clipRect);
    }
}

function createHAR(address, url, title, startTime, resources, page_cookies, b64_content, selectors, clickables)
{
    var entries = [];
    console.log("Getting request/responses...");
    resources.forEach(function (resource) {
        var request = resource.request,
            startReply = resource.startReply,
            endReply = resource.endReply;

        if (!request || !startReply || !endReply) {
            return;
        }

        // Exclude Data URI from HAR file because
        // they aren't included in specification
        // but moreover are of little use
        if (request.url.match(/(^data:image\/.*)/i)) {
            console.log("Ignoring data:image URL "+ request.url)
            return;
        }

        entries.push({
            startedDateTime: request.time.toISOString(),
            time: endReply.time - request.time,
            request: {
                method: request.method,
                url: request.url,
                httpVersion: "HTTP/1.1",
                cookies: [],
                headers: request.headers,
                queryString: [],
                headersSize: -1,
                bodySize: -1
            },
            response: {
                status: endReply.status,
                statusText: endReply.statusText,
                httpVersion: "HTTP/1.1",
                cookies: [],
                headers: endReply.headers,
                redirectURL: "",
                headersSize: -1,
                bodySize: startReply.bodySize,
                content: {
                    size: startReply.bodySize,
                    mimeType: endReply.contentType
                }
            },
            cache: {},
            timings: {
                blocked: 0,
                dns: -1,
                connect: -1,
                send: 0,
                wait: startReply.time - request.time,
                receive: endReply.time - startReply.time,
                ssl: -1
            },
            pageref: address
        });
    });

    // Reset to the full viewport:
    console.log("Resetting viewport...");
    setToFullViewport();

    // Render selected elements:
    console.log("Rendering selector(s) to PNG...");
    var renderedElements = [];
    selectors.forEach(function(selector) {
        var image = captureSelector(selector);
        if(image != null) {
            renderedElements.push({
                selector: selector,
                format: "PNG",
                content: image,
                encoding: "base64"
            });
        }
    });
    
    console.log("Returning result...");

    return {
        log: {
            version: '1.0.0',
            creator: {
                name: "PhantomJS",
                version: phantom.version.major + '.' + phantom.version.minor +
                    '.' + phantom.version.patch
            },
            pages: [{
                startedDateTime: startTime.toISOString(),
                id: address,
                url: url,
                title: title,
                pageTimings: {
                    onLoad: page.endTime - page.startTime
                },
                renderedContent: {
                    text: b64_content,
                    encoding: "base64"
                },
                renderedElements: renderedElements,
                map: clickables,
                cookies: page_cookies
            }],
            entries: entries
        }
    };
}


var doRender = function () {
    console.log("doRender...");
    page.endTime = new Date();
    page.title = page.evaluate(function () {
        return document.title;
    });
    console.log("Getting clickables...");
    var clickables = page.evaluate(function() {
        var clickables = [];
        var elements = Array.prototype.slice.call(document.getElementsByTagName("*"));
        elements.forEach(function(element) {
            if(element.offsetParent != null) {
                if(element.onclick != null || element.attributes["href"] != undefined) {
                    var c = {};
                    c.location = element.getBoundingClientRect();
                    if(element.attributes["href"] != undefined) {
                        // Get absolute URL:
                        c.href = element.href;
                    }
                    if(element.onclick != null) {
                        c.onclick = element.onclick.toString();
                    }
                    clickables.push(c);
                }
            }
        });
        return clickables;
    });
    var output = system.args[2];
    var selectors = system.args.slice(3);
    // Default to rendering the root element:
    if( selectors.length == 0 ) {
        selectors = [":root"]
    }
    console.log("Getting content...");
    var b64_content = window.btoa(unescape(encodeURIComponent(page.content)));
    console.log("Creating HAR...");
    var har = createHAR(page.address, page.url, page.title, page.startTime, page.resources, page.cookies, b64_content, selectors, clickables);
    console.log("C " + page.cookies)
    console.log("Writing HAR...");
    fs.write(output, JSON.stringify(har, undefined, 4), "w");
    
    console.log("Exiting...");
    phantom.exit();
};

var setToFullViewport = function() {
    // Reset scroll position (or you get a big blank image):
    page.scrollPosition = { top: 0, left: 0 };

    // Get the scrollHeight:
    scrollHeight = page.evaluate(function() {
            if( document.body != null) {
              return document.body.scrollHeight; 
            } else {
              return 0;
            }
    });
    if(scrollHeight == 0) return;
    console.log("INFO: Resizing viewport to scrollHeight: "+scrollHeight);
    page.viewportSize = {
        width: 1280,
        height: scrollHeight
    };
}

var autoScroller = function() {
    // Scroll down...
    scrollPosition = page.evaluate(function() {
        if( document.body != null) {
          return document.body.scrollTop; 
        } else {
          return 0;
        }
    });
    //console.log("INFO: Current scrollPosition: "+scrollPosition);
    page.scrollPosition = { top: scrollPosition+200, left: 0 };

    setTimeout(autoScroller, 200);
};

var page = require('webpage').create(),
    system = require('system'),
    count = 0,
    resourceWait  = 2000, 
    maxRenderWait = 30000,
    forcedRenderTimeout,
    renderTimeout;
    var fs = require("fs");

if (system.args.length === 1) {
    console.log('Usage: phantomjs-render.js URL output-file selectors...');
    phantom.exit(1);
} else {
    page.address = system.args[1];
    page.resources = [];

    // Set up optional user agent and target datetime from the environment.
    var env = system.env;

    Object.keys(env).forEach(function(key) {
      console.log(key + '=' + env[key]);
    });
    console.log("--------");

    // Add optional userAgent override:
    if( 'USER_AGENT' in env ) {
        page.settings.userAgent = env['USER_AGENT'];
        // e.g. 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2062.120 Safari/537.36';
    } else if( 'USER_AGENT_ADDITIONAL' in env ) {
        page.settings.userAgent = page.settings.userAgent + " " + env['USER_AGENT_ADDITIONAL']
    }

    // Set up an object for customHeaders:
    headers = {}

    // Add Memento Datetime header if needed:
    // e.g. Accept-Datetime: Thu, 31 May 2007 20:35:00 GMT
    if( 'MEMENTO_ACCEPT_DATETIME' in env ) {
        headers['Accept-Datetime'] = env['MEMENTO_ACCEPT_DATETIME']
    }

    // Add a warc-prefix as JSON in a Warcprox-Meta: header
    if( 'WARCPROX_WARC_PREFIX' in env ) {
        headers['Warcprox-Meta'] = '{ "warc-prefix": "'+env['WARCPROX_WARC_PREFIX']+'" }';
    }
    
    // And assign:
    page.customHeaders = headers;
    for(var key in page.customHeaders) {
      console.log('Custom header: ' + key + '=' + page.customHeaders[key]);
    };

    page.onLoadStarted = function () {
        page.startTime = new Date();
    };

    page.onResourceRequested = function (req) {
        count += 1;
        //console.log("Request initiated, so total = "+count);
        page.resources[req.id] = {
            request: req,
            startReply: null,
            endReply: null
        };
        clearTimeout(renderTimeout);
    };

    page.onResourceReceived = function (res) {
        if (res.stage === 'start') {
            page.resources[res.id].startReply = res;
        }
        if (res.stage === 'end') {
            page.resources[res.id].endReply = res;
        }
        //
         if(!res.stage || res.stage === 'end') {
            count -= 1;
            //console.log("Request complete, so total = "+count);

            // If all requests have been resolved - re-fit the viewport:
            if(count === 0) {
                // Optionally, keep resizing the viewport to be the whole page:
                // Current model is to autoscroll and do this at the end.
                // setToFullViewport();
                // Render the result, but wait in case more resources turn up.
                renderTimeout = setTimeout(doRender, resourceWait);
            }
        }
    };

    page.onLoadFinished = function() {
        console.log("INFO: onLoadFinished.");
    };

    page.onError = function (msg, trace) {
        console.log("ERROR:",msg);
        trace.forEach(function(item) {
            console.log("ERROR:", item.file, ':', item.line);
        })
    };

    page.onResourceError = function(resourceError) {
        console.error(resourceError.url + ': ' + resourceError.errorString);
    };

    page.onConsoleError = function (msg, trace) {
        console.log("ERROR:",msg);
        trace.forEach(function(item) {
            console.log("ERROR:", item.file, ':', item.line);
        })
    };    

    page.viewportSize = { width: 1280, height: 1024 };

    page.open(page.address, function (status) {
        // 'success' is not always reported properly, so just do the same wait-for-the-end no matter what.

        // Set the timeout till forcing a render:
        forcedRenderTimeout = setTimeout(function () {

            // Force an exit in case the load fails:
            setTimeout(function () {
                console.log("Forcing exit after awaiting render...");
                phantom.exit(0);
            }, maxRenderWait);

            // Now force the render:
            console.log("WARNING: Forcing rendering to complete...");
            doRender();

        }, maxRenderWait);
    });

    // Auto-scroll down:
    autoScroller();

}
