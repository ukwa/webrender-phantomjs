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
    }
    try {
        page.clipRect = clipRect;
        return page.renderBase64("PNG");
    } catch (e) {
        console.log("Failed to capture screenshot: " + e, "error");
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

function createHAR(address, title, startTime, resources, b64_content, selectors, clickables)
{
    var entries = [];
    resources.forEach(function (resource) {
        var request = resource.request,
            startReply = resource.startReply,
            endReply = resource.endReply;

        if (!request || !startReply || !endReply) {
            return;
        }

        // Exclude Data URI from HAR file because
        // they aren't included in specification
        if (request.url.match(/(^data:image\/.*)/i)) {
            //Include these; we're already breaking the spec.
            //return;
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

    return {
        log: {
            version: '0.0.2',
            creator: {
                name: "PhantomJS",
                version: phantom.version.major + '.' + phantom.version.minor +
                    '.' + phantom.version.patch
            },
            pages: [{
                startedDateTime: startTime.toISOString(),
                id: address,
                title: title,
                pageTimings: {
                    onLoad: page.endTime - page.startTime
                },
                renderedContent: {
                    text: b64_content,
                    encoding: "base64"
                },
                renderedElements: renderedElements,
                map: clickables
            }],
            entries: entries
        }
    };
}

var doRender = function () {
    page.endTime = new Date();
    page.title = page.evaluate(function () {
        return document.title;
    });
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
    var b64_content = window.btoa(unescape(encodeURIComponent(page.content)));
    var har = createHAR(page.address, page.title, page.startTime, page.resources, b64_content, selectors, clickables);
    fs.write(output, JSON.stringify(har, undefined, 4), "w");
    phantom.exit();
};

var page = require('webpage').create(),
    system = require('system'),
    count = 0,
    resourceWait  = 500, 
    maxRenderWait = 30000,
    forcedRenderTimeout,
    renderTimeout;
    var fs = require("fs");

if (system.args.length === 1) {
    console.log('Usage: netsniff-rasterize.js URL output-file selectors...');
    phantom.exit(1);
} else {
    page.address = system.args[1];
    page.resources = [];

    page.onLoadStarted = function () {
        page.startTime = new Date();
    };

    page.onResourceRequested = function (req) {
        count += 1;
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
         if(!res.stage || res.stage === "end") {
            count -= 1;
            page.viewportSize = {
                width: 1280,
                height: page.evaluate(function() {
                    return document.body.scrollHeight;
                })
            };
            if(count === 0) {
                renderTimeout = setTimeout(doRender, resourceWait);
            }
        }
    };

    page.viewportSize = { width: 1280, height: 960 };

    page.open(page.address, function (status) {
        if (status !== 'success') {
            console.log('FAIL to load the address');
            phantom.exit(1);
        } else {
            forcedRenderTimeout = setTimeout(function () {
                doRender();
            }, maxRenderWait);
        }
    });
}
