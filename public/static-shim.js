/*
 * Static-site shim for the revived bookmarked.co.in.
 *
 * The original pages were rendered by OpenCart and their JavaScript called store routes
 * (index.php?route=...) for the cart, wish list, compare, search, reviews, PIN check and
 * newsletter. There is no backend any more, so this file replaces those calls with a notice.
 * It sends nothing anywhere and stores nothing.
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

	// Theme functions referenced by onclick attributes. This file loads right after jQuery, before
	// the theme's common.js defines them, so they are replaced once the document is ready.
	$(function () {
		window.addToCart = notice;
		window.addToWishList = notice;
		window.addToCompare = notice;
		window.prepaidpincheck = notice;
	});

	function stop(e) {
		e.preventDefault();
		e.stopPropagation();
		notice();
	}

	// Capture-phase listeners run before any handler bound by the theme scripts, and stopping
	// propagation here keeps inline onclick/onchange handlers on the target from running.
	var CLICK_TARGETS = '.button-search, .button-search-mobile, #formNewLestter button, #button-cart, #button-review, [onclick^="prepaidpincheck"]';
	document.addEventListener('click', function (e) {
		var $t = $(e.target);
		if ($t.closest(CLICK_TARGETS).length) {
			stop(e);
		} else if ($t.closest('a[data-store-link]').length && !$t.closest('.dropdown-toggle').length) {
			// Links to store pages that were never archived (or are account/cart actions).
			stop(e);
		}
	}, true);

	// Sort / limit dropdowns navigate to the option value; '#' means that variant was not kept.
	document.addEventListener('change', function (e) {
		if ($(e.target).is('select') && e.target.value === '#') {
			stop(e);
		}
	}, true);

	// Search autocomplete would query the store; swallow key events before jQuery UI sees them.
	var SEARCH_INPUTS = 'input[name="search"], input[name="search_mobile"]';
	['keydown', 'keyup', 'keypress', 'input'].forEach(function (type) {
		document.addEventListener(type, function (e) {
			if ($(e.target).is(SEARCH_INPUTS)) {
				e.stopPropagation();
				if (type === 'keydown' && (e.keyCode || e.which) === 13) {
					stop(e);
				}
			}
		}, true);
	});

	document.addEventListener('submit', stop, true);
})(jQuery);
