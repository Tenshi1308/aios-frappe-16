app_name = "aios_v1"
app_title = "AIOS V1"
app_publisher = "Tenshi"
app_description = "AIOS Plugin SaaS"
app_email = "samuelkarel1308@gmail.com"
app_license = "mit"

# Send non-GET requests for this app's endpoints as native `application/json`
# bodies instead of form-encoded, per-key JSON-stringified values.
use_json_request_body = True

# AIOS identity setup (Custom Field User, Role, Role Profile).
after_install = "aios_v1.setup.after_install"
after_migrate = "aios_v1.setup.after_migrate"

# AIOS auth guard (Frappe login + every request).
on_login = "aios_v1.setup.on_login"
auth_hooks = ["aios_v1.setup.validate_aios_status"]

doc_events = {
    "User": {
        "validate": "aios_v1.setup.sync_aios_status_enabled",
    },
    "Pending Action Draft": {
        "before_insert": "aios_v1.permissions.set_draft_user",
    },
}

# Apps
# ------------------


# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "aios_v1",
# 		"logo": "/assets/aios_v1/logo.png",
# 		"title": "AIOS V1",
# 		"route": "/aios_v1",
# 		"has_permission": "aios_v1.api.permission.has_app_permission",
# 	}

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `aios_v1/dock/aios_v1/aios_v1.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/aios_v1/css/aios_v1.css"
# app_include_js = "/assets/aios_v1/js/aios_v1.js"

# include js, css files in header of web template
# web_include_css = "/assets/aios_v1/css/aios_v1.css"
# web_include_js = "/assets/aios_v1/js/aios_v1.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "aios_v1/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "aios_v1/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Setup Wizard
# ------------

# open a fresh site's setup in this app's own UI instead of the desk wizard.
# must be a non-desk route (not under /desk or /app); to customize setup within
# desk, use setup_wizard_stages / setup_wizard_complete instead.
# setup_wizard_url = "/aios_v1/setup"

# Generators
# ----------

# automatically create page for each record of this doctype

# automatically load and sync documents of this doctype from downstream apps

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "aios_v1.utils.jinja_methods",
# 	"filters": "aios_v1.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "aios_v1.install.before_install"
# after_install = "aios_v1.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "aios_v1.uninstall.before_uninstall"
# after_uninstall = "aios_v1.uninstall.after_uninstall"

# Disable / Enable
# ----------------
# Called when this app is logically disabled or re-enabled on a site,
# without uninstalling it. Use this to hide/restore fields this app adds
# to other apps' doctypes.

# before_disable = "aios_v1.uninstall.before_disable"
# after_disable = "aios_v1.uninstall.after_disable"
# before_enable = "aios_v1.install.before_enable"
# after_enable = "aios_v1.install.after_enable"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "aios_v1.utils.before_app_install"
# after_app_install = "aios_v1.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "aios_v1.utils.before_app_uninstall"
# after_app_uninstall = "aios_v1.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "aios_v1.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "aios_v1.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "aios_v1.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"AIOS Conversation": "aios_v1.permissions.conversation_query_conditions",
	"AIOS Agent State": "aios_v1.permissions.agent_state_query_conditions",
	"Pending Action Draft": "aios_v1.permissions.draft_query_conditions",
	"AIOS Message": "aios_v1.permissions.message_query_conditions",
	"AIOS Token Usage": "aios_v1.permissions.token_usage_query_conditions",
}

has_permission = {
	"AIOS Conversation": "aios_v1.permissions.has_permission",
	"AIOS Agent State": "aios_v1.permissions.has_permission",
	"Pending Action Draft": "aios_v1.permissions.has_permission",
	"AIOS Message": "aios_v1.permissions.has_permission",
	"AIOS Token Usage": "aios_v1.permissions.has_permission",
}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"aios_v1.services.usage.reset_daily_counters",
	],
}

# Testing
# -------

# before_tests = "aios_v1.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "aios_v1.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "aios_v1.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "aios_v1.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------


# Request Events
# ----------------

# Job Events
# ----------


# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"aios_v1.auth.validate"

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# Require all whitelisted methods to have type annotations
require_type_annotated_api_methods = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.







before_request = ['aios_v1.api.dispatcher.handle_api_request']
