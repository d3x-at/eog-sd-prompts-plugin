import os
import sys
from pathlib import Path
import pkg_resources

from .constants import PACKAGE_NAME

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "install":
        print('execute "python -m eog_sd_prompts_plugin install" to add a link to the user\'s eog plugin directory')
        sys.exit(1)

    plugins_dir = Path(os.getenv("XDG_DATA_HOME", Path(os.getenv("HOME"), ".local/share")),
                       "eog/plugins")

    package_path = os.path.join(
        pkg_resources.get_distribution(PACKAGE_NAME).location, PACKAGE_NAME)

    symlink_path = plugins_dir / PACKAGE_NAME

    if not plugins_dir.exists():
        plugins_dir.mkdir(parents=True, exist_ok=True)
        print(f'created EOG plugin directory: {plugins_dir}')

    os.symlink(package_path, symlink_path)
    print(f'created a symlink from {package_path} to {symlink_path}')
