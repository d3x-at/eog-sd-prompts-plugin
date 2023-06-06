import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Optional

import sdparsers

from gi.repository import Eog, Gdk, Gio, GObject, Gtk, PeasGtk

PACKAGE_NAME = "eog_sd_prompts_plugin"
PLUGIN_ID = "org.gnome.eog.plugins.sd-prompts"
PLUGIN_DIR = Path(os.getenv("XDG_DATA_HOME", os.path.join(os.getenv("HOME"), ".local/share")),
                  "eog/plugins", PACKAGE_NAME)

clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
parser = sdparsers.ParserManager()

CLIPBOARD_PARAMS = {
    sdparsers.AUTOMATIC1111Parser.GENERATOR_ID: "parameters",
    sdparsers.InvokeAIParser.GENERATOR_ID: "sd-metadata"
}


class SDPromptsPlugin(GObject.Object, Eog.WindowActivatable, PeasGtk.Configurable):
    window = GObject.property(type=Eog.Window)
    parameters: Optional[sdparsers.PromptInfo] = None
    settings_widget = None

    def __init__(self):
        self.settings = self._get_settings()

        self.ui = Gtk.Builder()
        self.ui.add_from_file(str(PLUGIN_DIR / "sd_prompts.glade"))

        self.info_label = self.ui.get_object("info-label")
        self.prompts_container = self.ui.get_object("prompts-container")

        self.button_copy_prompt = self.ui.get_object("copy-prompt-button")
        self.button_copy_prompt.connect("clicked", self._copy_prompt_cb)

    def do_activate(self) -> None:
        # initialize Gtk Components
        self.sidebar = self.ui.get_object("sd-prompts-root")
        if not self.sidebar:
            return

        # connect to EOG's image notifications
        self.image_loaded_id = self.window.get_view().connect(
            "notify::image", self._notify_image_cb)

        # add as a new sidebar
        self.window.get_sidebar().add_page("SD Prompt", self.sidebar)

        # try to display our new sidebar
        if self.settings and self.settings.get_boolean("set-page"):
            self.window.get_sidebar().set_page(self.sidebar)

    def do_deactivate(self) -> None:
        if self.sidebar:
            # Disconnect image notify callback
            self.window.get_view().disconnect(self.image_loaded_id)
            # remove our sidebar
            self.window.get_sidebar().remove_page(self.sidebar)

    def do_create_configure_widget(self):
        if self.settings is None:
            return None

        if self.settings_widget is None:
            self.settings_widget = self.ui.get_object("sd-prompts-config-box")
            set_page_checkbox = self.ui.get_object("set-page-checkbox")
            set_page_checkbox.connect("toggled", self._set_page_toggle_cb)
            set_page = self.settings.get_boolean("set-page")
            set_page_checkbox.set_active(set_page)
        return self.settings_widget

    def _set_page_toggle_cb(self, checkbox) -> None:
        self.settings.set_boolean("set-page", checkbox.get_active())

    def _get_settings(self):
        try:
            schema_source = Gio.SettingsSchemaSource.new_from_directory(
                str(PLUGIN_DIR), None, False)
            schema = schema_source.lookup(PLUGIN_ID, False)
            return Gio.Settings.new_full(schema, None, None)
        except Exception:
            logging.exception("could not load configuration")
        return None

    def _copy_prompt_cb(self, _) -> None:
        '''copy prompt information to clipboard (if available)'''
        if not self.parameters:
            return
        param_key = CLIPBOARD_PARAMS.get(self.parameters.generator)
        if param_key:
            clipboard.set_text(
                self.parameters.raw_params[param_key], -1)

    def _notify_image_cb(self, *_) -> None:
        '''handle image notifications'''
        image = self.window.get_image()
        if image:
            image_file = image.get_file()
            image_file.load_bytes_async(None, self._load_bytes_complete)

    def _load_bytes_complete(self, file, result):
        bytes = file.load_bytes_finish(result)
        try:
            with BytesIO(bytes[0].get_data()) as image_io:
                parameters = parser.parse(image_io)
            self._set_parameters(parameters)
        except Exception:  # pylint: disable=broad-except
            logging.exception('error while reading image')

    def _set_parameters(self, parameters) -> None:
        '''query the image for SD parameters and fill fields'''
        self.parameters = parameters

        if not self.parameters:
            self.info_label.set_label("No SD metadata found.")
            self.prompts_container.set_visible(False)
            return

        # info label & copy to clipboard button
        self.info_label.set_label(f"Generator: {self.parameters.generator}")
        self.prompts_container.set_visible(True)
        self.button_copy_prompt.set_visible(
            self.parameters.generator in CLIPBOARD_PARAMS)

        # positive prompt
        prompts = (prompt.value for prompt,
                   _ in self.parameters.prompts if prompt)
        prompt_label = self.ui.get_object("prompt")
        prompt_label.set_label("\n\n".join(prompts))

        # negative prompt
        negative_prompts = (prompt.value for _,
                            prompt in self.parameters.prompts if prompt)
        negative_prompt_label = self.ui.get_object("negative-prompt")
        negative_prompt_label.set_label("\n\n".join(negative_prompts))

        # additional metadata
        parameters_box = self.ui.get_object("parameters-box")
        # empty the parameters box before adding parameters
        for child in parameters_box.get_children():
            parameters_box.remove(child)

        # models
        for model_name, model_hash in {(model.name, model.model_hash)
                                       for model in self.parameters.models}:
            if model_name:
                parameters_box.add(key_value_box("Model", model_name))
            if model_hash:
                parameters_box.add(key_value_box("Model Hash", model_hash))

        # samplers
        samplers = {sampler.name for sampler in self.parameters.samplers}
        parameters_box.add(key_value_box("Samplers", ", ".join(samplers)))

        # sampler parameters (only for single-sampler images)
        if len(self.parameters.samplers) == 1:
            sampler = self.parameters.samplers[0]
            for key, value in sampler.parameters.items():
                parameters_box.add(key_value_box(key, value))

        # fill parameters box with new items
        for key, value in self.parameters.metadata.items():
            if isinstance(value, (dict, list)):
                continue
            parameters_box.add(key_value_box(key, value))

        parameters_box.show_all()


def key_value_box(key: str, value: Optional[str] = None):
    '''returns a Gtk.Box containing a `key: value` pair'''
    key = key.replace("_", " ").title()
    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
    label1 = Gtk.Label(f'{key}:', xalign=0, yalign=0,
                       sensitive=False, selectable=True)
    hbox.add(label1)
    if value:
        label2 = Gtk.Label(value, xalign=0, yalign=0, selectable=True)
        label2.set_line_wrap(True)
        hbox.add(label2)
    return hbox
