import os
import logging
from pathlib import Path
from typing import Optional
from gi.repository import Eog, Gdk, GObject, Gtk

import sdparsers as parser

PACKAGE_NAME = "eog_sd_prompts_plugin"
PLUGIN_ID = "org.gnome.eog.plugins.sd-prompts"
PLUGIN_DIR = Path(os.getenv("XDG_DATA_HOME", os.path.join(os.getenv("HOME"), ".local/share")),
                  "eog/plugins", PACKAGE_NAME)

clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

CLIPBOARD_PARAMS = {
    parser.AUTOMATIC1111Parser.GENERATOR_ID: "parameters",
    parser.AUTOMATICStealthParser.GENERATOR_ID: "parameters",
    parser.InvokeAIParser.GENERATOR_ID: "sd-metadata"
}


class SDPromptsPlugin(GObject.Object, Eog.WindowActivatable):
    window = GObject.property(type=Eog.Window)
    parameters: Optional[parser.PromptInfo] = None

    def __init__(self):
        self.parser = parser.ParserManager()
        self.ui = Gtk.Builder()
        self.ui.add_from_file(str(PLUGIN_DIR / "sd_prompts.glade"))

        self.info_label = self.ui.get_object("info-label")
        self.prompts_container = self.ui.get_object("prompts-container")

        self.button_copy_prompt = self.ui.get_object("copy-prompt-button")
        self.button_copy_prompt.connect("clicked", self.copy_prompt)

    def do_activate(self) -> None:
        # initialize Gtk Components
        self.sidebar = self.ui.get_object("sd-prompts-root")
        if self.sidebar is None:
            return

        # connect to EOG's image notifications
        self.image_loaded_id = self.window.get_view().connect(
            "notify::image", self.notify_image_cb)

        # add as a new sidebar
        self.window.get_sidebar().add_page("SD Prompt", self.sidebar)

        # try to display our new sidebar
        self.window.get_sidebar().set_page(self.sidebar)

    def do_deactivate(self) -> None:
        if self.sidebar is not None:
            # Disconnect image notify callback
            self.window.get_view().disconnect(self.image_loaded_id)
            # remove our sidebar
            self.window.get_sidebar().remove_page(self.sidebar)

    def notify_image_cb(self, *_) -> None:
        '''handle image notifications'''
        image = self.window.get_image()
        if image is not None:
            self.set_parameters(image)

    def copy_prompt(self, _) -> None:
        '''copy prompt to clipboard'''
        if self.parameters is not None:
            param_key = CLIPBOARD_PARAMS.get(self.parameters.generator)
            if param_key:
                clipboard.set_text(
                    self.parameters.raw_params[param_key], -1)

    def set_parameters(self, image):
        self.parameters = self.get_parameters(image)

        if self.parameters is None:
            self.info_label.set_label("No SD metadata found.")
            self.prompts_container.set_visible(False)
            return

        self.info_label.set_label(f"Generator: {self.parameters.generator}")
        self.prompts_container.set_visible(True)

        self.button_copy_prompt.set_visible(
            self.parameters.generator in CLIPBOARD_PARAMS)

        prompts = []
        negative_prompts = []
        for prompt, negative_prompt in self.parameters.prompts:
            if prompt:
                prompts.append(prompt.value)
            if negative_prompt:
                negative_prompts.append(negative_prompt.value)

        # positive prompt
        prompt_label = self.ui.get_object("prompt")
        prompt_label.set_label("\n\n".join(prompts))

        # negative prompt
        negative_prompt_label = self.ui.get_object("negative-prompt")
        negative_prompt_label.set_label("\n\n".join(negative_prompts))

        parameters_box = self.ui.get_object("parameters-box")
        # clean up additional parameters
        for child in parameters_box.get_children():
            parameters_box.remove(child)

        # models
        models = { (model.name, model.model_hash) for model in self.parameters.models }
        for model_name, model_hash in models:
            if model_name:
                parameters_box.add(key_value_box("Model", model_name))
            if model_hash:
                parameters_box.add(key_value_box("Model Hash", model_hash))

        # samplers
        num_samplers = len(self.parameters.samplers) 
        if num_samplers > 1:
            parameters_box.add(key_value_box("Sampler", f"Multiple ({num_samplers})"))
        elif num_samplers > 0:
            sampler = self.parameters.samplers[0]
            parameters_box.add(key_value_box("Sampler", sampler.name))
            for key, value in sampler.parameters.items():
                parameters_box.add(key_value_box(key, value))

        # fill parameters box with new items
        for key, value in self.parameters.metadata.items():
            if not isinstance(value, (str, int, bool)):
                continue
            parameters_box.add(key_value_box(key, value))

        parameters_box.show_all()


    def get_parameters(self, eog_image) -> Optional[parser.PromptInfo]:
        '''try to get sd prompts from the given image'''
        image_file = eog_image.get_file()
        image_info = image_file.query_info('standard::content-type', 0, None)
        mime_type = image_info.get_content_type()
        parameters = None

        if mime_type in ("image/png", "image/jpeg", "image/webp"):
            image_path = image_file.get_path()
            try:
                parameters = self.parser.parse(image_path)
            except Exception:  # pylint: disable=broad-except
                logging.exception('error while reading %s', image_path)

        return parameters

def key_value_box(key, value):
    key = key.replace("_", " ").title()
    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
    hbox.add(Gtk.Label(
        f'{key}:', xalign=0, sensitive=False, selectable=True))
    hbox.add(Gtk.Label(value, xalign=0, selectable=True))
    return hbox