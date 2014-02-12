/*
 * Based on this: https://gist.github.com/n1k0/1501173
 */

var page = new WebPage(),
address, output, size;

capture = function( targetFile, clipRect ) {
	if ( clipRect ) {
		if ( !typeof( clipRect ) === "object" ) {
			throw new Error( "clipRect must be an Object instance." );
		}
		console.log( "Capturing page to " + targetFile + " with clipRect" + JSON.stringify( clipRect ), "debug" );
	} else {
		console.log( "Capturing page to " + targetFile, "debug" );
	}
	try {
		page.clipRect = clipRect;
		page.render( targetFile );
	} catch( e ) {
		console.log( "Failed to capture screenshot as " + targetFile + ": " + e, "error" );
	}
	return this;
}

captureSelector = function( targetFile, selector ) {
	var clipRect = page.evaluate( function( selector ) {
		return document.querySelector( selector ).getBoundingClientRect();
	}, selector );
	return capture( targetFile, clipRect );
}

if ( phantom.args.length == 0 ) {
	console.log( "Usage: domimage.js url selectors" );
	phantom.exit();
} else {
	address = phantom.args[ 0 ];
	page.viewportSize = { width: 1280, height: 960 };
	page.paperSize = { width: 1280, height: 960, border: "0px" }
	page.open( address, function ( status ) {
		if ( status !== "success" ) {
			console.log( "Unable to load the address!" );
			console.log( status );
		} else {
			var selectors = phantom.args.slice( 1 );
			for ( var i = 0; i < selectors.length; i++ ){
				var sel = selectors[ i ];
				var targetFile = encodeURIComponent( sel + ".png" );
				captureSelector( targetFile, sel ) ;
			}
			phantom.exit();
		}
	} );
}
