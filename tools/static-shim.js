/*
 * Static-site shim for the revived bookmarked.co.in homepage.
 *
 * The original page was rendered by OpenCart and its JavaScript called store routes
 * (index.php?route=...) for the cart, wish list, compare, search, quick view and newsletter.
 * There is no backend any more, so this file replaces those calls with a notice. It sends
 * nothing anywhere and stores nothing.
 */
(function ($) {
	var MESSAGE = 'Bookmarked is being revived. Online ordering is not available yet.';

	function notice() {
		$('#notification').html('<div class="attention" style="display: none;">' + MESSAGE + '</div>');
		$('#notification .attention').fadeIn('slow');
		$('html, body').animate({ scrollTop: 0 }, 'slow');
		return false;
	}

	// Defense in depth: no request may leave the page through jQuery.
	$.ajaxPrefilter(function (options, original, xhr) {
		xhr.abort();
	});

	// Theme functions referenced by the product cards' onclick attributes.
	window.addToCart = notice;
	window.addToWishList = notice;
	window.addToCompare = notice;

	// Capture-phase listeners run before any jQuery handler bound by the theme scripts.
	var CLICK_TARGETS = '.pav-colorbox, .button-search, .button-search-mobile, #formNewLestter button';
	document.addEventListener('click', function (e) {
		if ($(e.target).closest(CLICK_TARGETS).length) {
			e.preventDefault();
			e.stopPropagation();
			notice();
		} else if ($(e.target).closest('a[data-store-link]').length && !$(e.target).closest('.dropdown-toggle').length) {
			// Links to store pages (account, categories, products) that no longer exist.
			e.preventDefault();
			notice();
		}
	}, true);

	// Search autocomplete would query the store; swallow key events before jQuery UI sees them.
	var SEARCH_INPUTS = 'input[name="search"], input[name="search_mobile"]';
	['keydown', 'keyup', 'keypress', 'input'].forEach(function (type) {
		document.addEventListener(type, function (e) {
			if ($(e.target).is(SEARCH_INPUTS)) {
				e.stopPropagation();
				if (type === 'keydown' && (e.keyCode || e.which) === 13) {
					e.preventDefault();
					notice();
				}
			}
		}, true);
	});

	document.addEventListener('submit', function (e) {
		e.preventDefault();
		e.stopPropagation();
		notice();
	}, true);
})(jQuery);
