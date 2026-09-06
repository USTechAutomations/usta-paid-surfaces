<?php
/**
 * Plugin Name: WP Accessibility Scan
 * Description: Flags missing alt text, empty links, missing form labels, missing lang, heading skips, duplicate ids and low-contrast inline colours on your own pages. Automated checks find some of the issues the guidelines describe, not all.
 * Version: 0.1.0
 * Requires at least: 6.0
 * Requires PHP: 7.4
 * Author: US Tech Automations
 * License: GPLv2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: wp-accessibility-scan
 *
 * This file is part of WP Accessibility Scan.
 * WP Accessibility Scan is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 2 of the License, or
 * (at your option) any later version.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function wp_accessibility_scan_menu() {
	add_management_page(
		'Accessibility scan',
		'Accessibility scan',
		'manage_options',
		'wp-accessibility-scan',
		'wp_accessibility_scan_screen'
	);
}
add_action( 'admin_menu', 'wp_accessibility_scan_menu' );

function wp_accessibility_scan_register() {
	register_setting(
		'wp_accessibility_scan',
		'wp_accessibility_scan_show_hosted',
		array(
			'type'              => 'string',
			'sanitize_callback' => 'wp_accessibility_scan_sanitize_flag',
			'default'           => '0',
		)
	);
}
add_action( 'admin_init', 'wp_accessibility_scan_register' );

function wp_accessibility_scan_sanitize_flag( $value ) {
	return ( '1' === (string) $value ) ? '1' : '0';
}

function wp_accessibility_scan_same_host( $url ) {
	$home = wp_parse_url( home_url( '/' ), PHP_URL_HOST );
	$got  = wp_parse_url( $url, PHP_URL_HOST );
	if ( ! $home || ! $got ) {
		return false;
	}
	return strtolower( $home ) === strtolower( $got );
}

function wp_accessibility_scan_hex( $val ) {
	$val = strtolower( trim( (string) $val ) );
	if ( preg_match( '/^#([0-9a-f]{3})$/', $val, $m ) ) {
		$h = $m[1];
		return array(
			hexdec( $h[0] . $h[0] ),
			hexdec( $h[1] . $h[1] ),
			hexdec( $h[2] . $h[2] ),
		);
	}
	if ( preg_match( '/^#([0-9a-f]{6})$/', $val, $m ) ) {
		$h = $m[1];
		return array(
			hexdec( substr( $h, 0, 2 ) ),
			hexdec( substr( $h, 2, 2 ) ),
			hexdec( substr( $h, 4, 2 ) ),
		);
	}
	if ( preg_match( '/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/', $val, $m ) ) {
		return array( (int) $m[1], (int) $m[2], (int) $m[3] );
	}
	return null;
}

function wp_accessibility_scan_lum( $rgb ) {
	$out = array();
	foreach ( $rgb as $c ) {
		$x = max( 0, min( 255, (int) $c ) ) / 255.0;
		$out[] = ( $x <= 0.04045 ) ? ( $x / 12.92 ) : pow( ( $x + 0.055 ) / 1.055, 2.4 );
	}
	return 0.2126 * $out[0] + 0.7152 * $out[1] + 0.0722 * $out[2];
}

function wp_accessibility_scan_ratio( $a, $b ) {
	$ca = wp_accessibility_scan_hex( $a );
	$cb = wp_accessibility_scan_hex( $b );
	if ( ! $ca || ! $cb ) {
		return null;
	}
	$l1 = wp_accessibility_scan_lum( $ca );
	$l2 = wp_accessibility_scan_lum( $cb );
	$hi = max( $l1, $l2 );
	$lo = min( $l1, $l2 );
	return ( $hi + 0.05 ) / ( $lo + 0.05 );
}

function wp_accessibility_scan_style_colours( $style ) {
	$color = '';
	$bg    = '';
	foreach ( explode( ';', (string) $style ) as $part ) {
		if ( strpos( $part, ':' ) === false ) {
			continue;
		}
		list( $k, $v ) = explode( ':', $part, 2 );
		$k = strtolower( trim( $k ) );
		$v = trim( $v );
		if ( 'color' === $k ) {
			$color = $v;
		} elseif ( 'background-color' === $k || 'background' === $k ) {
			if ( 0 !== strpos( strtolower( $v ), 'url' ) ) {
				$bits = preg_split( '/\s+/', $v );
				$bg   = $bits[0];
			}
		}
	}
	return array( $color, $bg );
}

function wp_accessibility_scan_snip( $el ) {
	if ( ! $el ) {
		return '';
	}
	$tag = strtolower( $el->tagName );
	$out = '<' . $tag;
	if ( $el->hasAttribute( 'href' ) ) {
		$out .= ' href="' . $el->getAttribute( 'href' ) . '"';
	}
	if ( $el->hasAttribute( 'src' ) ) {
		$out .= ' src="' . $el->getAttribute( 'src' ) . '"';
	}
	if ( $el->hasAttribute( 'name' ) ) {
		$out .= ' name="' . $el->getAttribute( 'name' ) . '"';
	}
	if ( $el->hasAttribute( 'id' ) ) {
		$out .= ' id="' . $el->getAttribute( 'id' ) . '"';
	}
	$out .= '>';
	if ( strlen( $out ) > 120 ) {
		$out = substr( $out, 0, 119 ) . '…';
	}
	return $out;
}

function wp_accessibility_scan_text( $el ) {
	$text = trim( preg_replace( '/\s+/', ' ', $el->textContent ) );
	$imgs = $el->getElementsByTagName( 'img' );
	for ( $i = 0; $i < $imgs->length; $i++ ) {
		$alt = trim( $imgs->item( $i )->getAttribute( 'alt' ) );
		if ( $alt ) {
			$text .= ' ' . $alt;
		}
	}
	return trim( $text );
}

function wp_accessibility_scan_checks( $html ) {
	$findings = array();
	$dom      = new DOMDocument();
	$prev     = libxml_use_internal_errors( true );
	$dom->loadHTML( $html, LIBXML_NOERROR | LIBXML_NOWARNING );
	libxml_clear_errors();
	libxml_use_internal_errors( $prev );

	$html_el = $dom->getElementsByTagName( 'html' )->item( 0 );
	$lang    = $html_el ? trim( $html_el->getAttribute( 'lang' ) ) : '';
	if ( $html_el && $html_el->hasAttribute( 'xml:lang' ) && ! $lang ) {
		$lang = trim( $html_el->getAttribute( 'xml:lang' ) );
	}
	if ( ! $lang ) {
		$findings[] = array(
			'rule'    => 'html-lang',
			'element' => '<html>',
			'fix'     => 'Add a lang attribute on the html tag, for example lang="en".',
		);
	}

	$imgs = $dom->getElementsByTagName( 'img' );
	for ( $i = 0; $i < $imgs->length; $i++ ) {
		$el = $imgs->item( $i );
		if ( ! $el->hasAttribute( 'alt' ) ) {
			$findings[] = array(
				'rule'    => 'img-alt',
				'element' => wp_accessibility_scan_snip( $el ),
				'fix'     => 'Add an alt attribute that names what the image shows, or alt="" if it is only decoration.',
			);
		}
	}

	$links = $dom->getElementsByTagName( 'a' );
	for ( $i = 0; $i < $links->length; $i++ ) {
		$el = $links->item( $i );
		$text = wp_accessibility_scan_text( $el );
		$aria = trim( $el->getAttribute( 'aria-label' ) );
		if ( '' === $text && '' === $aria ) {
			$findings[] = array(
				'rule'    => 'empty-link',
				'element' => wp_accessibility_scan_snip( $el ),
				'fix'     => 'Put visible text or an aria-label on the link so a reader knows where it goes.',
			);
		}
	}

	$buttons = $dom->getElementsByTagName( 'button' );
	for ( $i = 0; $i < $buttons->length; $i++ ) {
		$el = $buttons->item( $i );
		$text = wp_accessibility_scan_text( $el );
		$aria = trim( $el->getAttribute( 'aria-label' ) );
		if ( '' === $text && '' === $aria ) {
			$findings[] = array(
				'rule'    => 'empty-button',
				'element' => wp_accessibility_scan_snip( $el ),
				'fix'     => 'Put visible text or an aria-label on the button.',
			);
		}
	}

	$xpath = new DOMXPath( $dom );
	$fors  = array();
	foreach ( $xpath->query( '//label[@for]' ) as $lab ) {
		$fors[ $lab->getAttribute( 'for' ) ] = true;
	}
	$fields = $xpath->query( '//input|//select|//textarea' );
	foreach ( $fields as $el ) {
		$typ = strtolower( $el->getAttribute( 'type' ) );
		if ( 'input' === strtolower( $el->tagName ) && in_array( $typ, array( 'hidden', 'submit', 'button', 'reset', 'image' ), true ) ) {
			continue;
		}
		if ( trim( $el->getAttribute( 'aria-label' ) ) || trim( $el->getAttribute( 'aria-labelledby' ) ) || trim( $el->getAttribute( 'title' ) ) ) {
			continue;
		}
		$iid = $el->getAttribute( 'id' );
		if ( $iid && isset( $fors[ $iid ] ) ) {
			continue;
		}
		$wrap = $el;
		$inside_label = false;
		while ( $wrap && $wrap->parentNode ) {
			$wrap = $wrap->parentNode;
			if ( $wrap instanceof DOMElement && 'label' === strtolower( $wrap->tagName ) ) {
				$inside_label = true;
				break;
			}
		}
		if ( $inside_label ) {
			continue;
		}
		$findings[] = array(
			'rule'    => 'form-label',
			'element' => wp_accessibility_scan_snip( $el ),
			'fix'     => 'Tie a label to this field with for/id, wrap it in a label, or add aria-label.',
		);
	}

	$heads = $xpath->query( '//h1|//h2|//h3|//h4|//h5|//h6' );
	$prev  = 0;
	foreach ( $heads as $el ) {
		$level = (int) substr( strtolower( $el->tagName ), 1 );
		if ( $prev && $level > $prev + 1 ) {
			$findings[] = array(
				'rule'    => 'heading-skip',
				'element' => wp_accessibility_scan_snip( $el ),
				'fix'     => 'Do not skip heading levels; follow h1 with h2, then h3.',
			);
		}
		$prev = $level;
	}

	$seen = array();
	foreach ( $xpath->query( '//*[@id]' ) as $el ) {
		$iid = $el->getAttribute( 'id' );
		if ( isset( $seen[ $iid ] ) ) {
			$findings[] = array(
				'rule'    => 'duplicate-id',
				'element' => 'id="' . $iid . '"',
				'fix'     => 'Give each id a unique value on the page.',
			);
		} else {
			$seen[ $iid ] = true;
		}
	}

	foreach ( $xpath->query( '//*[@style]' ) as $el ) {
		list( $color, $bg ) = wp_accessibility_scan_style_colours( $el->getAttribute( 'style' ) );
		if ( ! $color || ! $bg ) {
			continue;
		}
		$ratio = wp_accessibility_scan_ratio( $color, $bg );
		if ( null !== $ratio && $ratio < 4.5 ) {
			$findings[] = array(
				'rule'    => 'low-contrast',
				'element' => wp_accessibility_scan_snip( $el ),
				'fix'     => 'Raise the contrast between text colour and background to at least 4.5 to 1.',
			);
		}
	}

	return $findings;
}

function wp_accessibility_scan_screen() {
	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}

	$notice   = '';
	$findings = array();
	$target   = home_url( '/' );

	if ( isset( $_POST['wp_accessibility_scan_save'] ) ) {
		check_admin_referer( 'wp_accessibility_scan_settings' );
		$flag = isset( $_POST['wp_accessibility_scan_show_hosted'] ) ? '1' : '0';
		update_option( 'wp_accessibility_scan_show_hosted', $flag );
		$notice = 'Setting saved.';
	}

	if ( isset( $_POST['wp_accessibility_scan_go'] ) ) {
		check_admin_referer( 'wp_accessibility_scan_run' );
		$raw = isset( $_POST['wp_accessibility_scan_url'] ) ? wp_unslash( $_POST['wp_accessibility_scan_url'] ) : '';
		$url = esc_url_raw( $raw );
		if ( ! $url ) {
			$url = home_url( '/' );
		}
		$target = $url;
		if ( ! wp_accessibility_scan_same_host( $url ) ) {
			$notice = 'That URL is not on this site. Checks only run on your own pages.';
		} else {
			$resp = wp_remote_get(
				$url,
				array(
					'timeout'     => 15,
					'redirection' => 3,
					'headers'     => array( 'Accept' => 'text/html' ),
				)
			);
			if ( is_wp_error( $resp ) ) {
				$notice = 'Could not fetch that page: ' . $resp->get_error_message();
			} else {
				$code = (int) wp_remote_retrieve_response_code( $resp );
				$body = wp_remote_retrieve_body( $resp );
				if ( 200 !== $code || '' === (string) $body ) {
					$notice = 'Could not read that page (HTTP ' . $code . ').';
				} else {
					$findings = wp_accessibility_scan_checks( $body );
					$notice   = 'Checked ' . $url . '. ' . count( $findings ) . ' finding(s). Automated checks find some of the issues the guidelines describe, not all.';
				}
			}
		}
	}

	$show = get_option( 'wp_accessibility_scan_show_hosted', '0' );
	echo '<div class="wrap">';
	echo '<h1>Accessibility scan</h1>';
	echo '<p>This plugin checks pages on <em>this</em> site. It is not a legal certificate. Automated checks find some of the issues the guidelines describe, not all.</p>';
	if ( $notice ) {
		echo '<div class="notice notice-info"><p>' . esc_html( $notice ) . '</p></div>';
	}

	echo '<h2>Run a check</h2>';
	echo '<form method="post">';
	wp_nonce_field( 'wp_accessibility_scan_run' );
	echo '<p><label for="wp_accessibility_scan_url">Page URL on this site</label><br />';
	echo '<input type="url" class="regular-text" id="wp_accessibility_scan_url" name="wp_accessibility_scan_url" value="' . esc_attr( $target ) . '" /></p>';
	submit_button( 'Run checks', 'primary', 'wp_accessibility_scan_go', false );
	echo '</form>';

	if ( $findings ) {
		echo '<table class="widefat striped"><thead><tr><th>Rule</th><th>Element</th><th>Fix</th></tr></thead><tbody>';
		foreach ( $findings as $row ) {
			echo '<tr><td>' . esc_html( $row['rule'] ) . '</td>';
			echo '<td><code>' . esc_html( $row['element'] ) . '</code></td>';
			echo '<td>' . esc_html( $row['fix'] ) . '</td></tr>';
		}
		echo '</tbody></table>';
	} elseif ( isset( $_POST['wp_accessibility_scan_go'] ) && wp_accessibility_scan_same_host( $target ) && ! $notice ) {
		echo '<p>No findings on that page.</p>';
	}

	echo '<h2>Weekly hosted scan</h2>';
	echo '<form method="post">';
	wp_nonce_field( 'wp_accessibility_scan_settings' );
	echo '<p><label><input type="checkbox" name="wp_accessibility_scan_show_hosted" value="1" ' . checked( $show, '1', false ) . ' /> ';
	echo 'Show a link to the weekly hosted scan page (off by default; this plugin never calls that page itself).</label></p>';
	submit_button( 'Save setting', 'secondary', 'wp_accessibility_scan_save', false );
	echo '</form>';
	if ( '1' === $show ) {
		echo '<p><a href="https://ustechautomations.com/feeds/wp-accessibility-scan">Weekly hosted scan of your whole public site</a></p>';
	}
	echo '</div>';
}
