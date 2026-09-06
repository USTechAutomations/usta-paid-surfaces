=== WP Accessibility Scan ===
Contributors: ustechautomations
Tags: accessibility, a11y, wcag, headings, alt-text
Requires at least: 6.0
Tested up to: 6.8
Stable tag: 0.1.0
Requires PHP: 7.4
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Flags missing alt text, empty links, missing labels, heading skips, duplicate ids and low-contrast inline colours on your own pages.

== Description ==

WP Accessibility Scan is a free tool for WordPress site owners. It adds a Tools screen that fetches a page on your own site and lists findings a person can act on.

Checks (all free, no key):

* images without an alt attribute
* empty links and empty buttons
* form fields without a label
* missing lang on the html tag
* heading level skips
* duplicate ids
* low-contrast inline colours, when both colours are set and can be read

Automated checks find some of the issues the guidelines describe, not all. This plugin does not claim legal compliance and does not change how the front of your site looks.

A settings checkbox (off by default) can show a link to a separate weekly hosted scan that runs from our machine and emails a site-wide report file. That hosted scan is a paid service. The plugin itself does not call our servers. When the checkbox is off, the only network request is your site fetching its own pages.

== Installation ==

1. Upload the `wp-accessibility-scan` folder to `/wp-content/plugins/`.
2. Activate the plugin through the Plugins screen.
3. Open Tools → Accessibility scan.
4. Leave the hosted-scan link checkbox off unless you want that link shown.

== Frequently Asked Questions ==

= Does this make my site legally compliant? =

No. Automated checks find some of the issues the guidelines describe, not all. Hand the report to a person.

= Do I need a key? =

No. Every check in this plugin runs without a key.

= Does the plugin phone home? =

No. A checkbox (off by default) can show a link to our hosted scan page. That is a link, not a request from this plugin.

= What is the weekly hosted scan? =

A separate paid service. Our machine fetches public pages of a site you name, runs the same class of checks, and emails a CSV. The plugin keeps working if you never buy that.

== Changelog ==

= 0.1.0 =
* First release.

== Upgrade Notice ==

= 0.1.0 =
First release.
