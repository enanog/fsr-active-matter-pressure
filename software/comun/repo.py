"""Make sure the data folder of the repository is known before a GUI app builds its windows."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from comun import paths


def ensure_repo(app_name: str, parent: QWidget | None = None) -> bool:
    """True when paths.REPO_ROOT points at the repository (has datos/). Otherwise asks for the
    folder once and remembers it (~/.proyecto_presion.json). Call before importing the windows."""
    if paths.REPO_FOUND:
        return True
    QMessageBox.information(
        parent, app_name,
        "No se encontró la carpeta del proyecto (la que contiene datos/presion y datos/video).\n\n"
        "Elegila a continuación; se recuerda para las próximas veces. Para no tener que elegirla, "
        "dejá el .exe dentro de la carpeta del proyecto o definí la variable de entorno "
        f"{paths.ENV_VAR}.")
    while True:
        d = QFileDialog.getExistingDirectory(parent, f"{app_name}: carpeta del proyecto", str(Path.home()))
        if not d:
            return False
        if paths.is_repo(Path(d)):
            paths.set_repo_root(Path(d), remember=True)
            return True
        QMessageBox.warning(parent, app_name, f"'{d}' no contiene datos/presion ni datos/video.")
