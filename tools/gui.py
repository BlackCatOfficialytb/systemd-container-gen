#!/usr/bin/env python3
"""GUI for rendering and building systemd container images at home."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.common import (
    build_image,
    default_target_image,
    distros,
    render,
    run_test,
    supported_tags,
)

RUNTIMES = ("auto", "docker", "podman")
YES_NO = ("yes", "no")


class Builder:
    """A simple tkinter UI for building one local systemd image."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("systemd-container-gen builder")
        self.queue: queue.Queue = queue.Queue()
        self.status = tk.StringVar()

        form = ttk.Frame(self.root, padding=10)
        form.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        ttk.Label(form, text="Distro:").grid(row=0, column=0, sticky="e")
        self.distro = ttk.Combobox(
            form,
            state="readonly",
            values=list(distros()),
        )
        self.distro.current(0)
        self.distro.grid(row=0, column=1, sticky="w", padx=5)
        self.distro.bind("<<ComboboxSelected>>", lambda _event: self._on_distro())

        ttk.Label(form, text="Upstream tag:").grid(row=1, column=0, sticky="e")
        self.tag = ttk.Combobox(form, state="readonly", values=supported_tags("ubuntu"))
        self.tag.current(0)
        self.tag.grid(row=1, column=1, sticky="w", padx=5)

        ttk.Label(form, text="Target image:").grid(row=2, column=0, sticky="e")
        self.target_image = ttk.Entry(form)
        self.target_image.grid(row=2, column=1, sticky="w", padx=5)
        self.target_image.insert(0, default_target_image("ubuntu"))

        ttk.Label(form, text="Runtime:").grid(row=3, column=0, sticky="e")
        self.runtime = ttk.Combobox(form, state="readonly", values=list(RUNTIMES))
        self.runtime.current(0)
        self.runtime.grid(row=3, column=1, sticky="w", padx=5)

        ttk.Label(form, text="Skip build:").grid(row=4, column=0, sticky="e")
        self.skip_build = ttk.Combobox(form, state="readonly", values=list(YES_NO))
        self.skip_build.current(1)
        self.skip_build.grid(row=4, column=1, sticky="w", padx=5)

        ttk.Label(form, text="Run test:").grid(row=5, column=0, sticky="e")
        self.test = ttk.Combobox(form, state="readonly", values=list(YES_NO))
        self.test.current(1)
        self.test.grid(row=5, column=1, sticky="w", padx=5)

        ttk.Button(form, text="Render", command=self.on_render).grid(
            row=6, column=0, columnspan=2, pady=5, sticky="ew"
        )
        ttk.Button(form, text="Build", command=self.on_build).grid(
            row=7, column=0, columnspan=2, pady=5, sticky="ew"
        )
        ttk.Label(self.root, textvariable=self.status).grid(
            row=1, column=0, sticky="ew", padx=10, pady=5
        )

        self.root.grid_rowconfigure(1, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

    def _on_distro(self) -> None:
        distro = self.distro.get()
        self.tag["values"] = supported_tags(distro)
        self.tag.set(supported_tags(distro)[0] if supported_tags(distro) else "")
        self.target_image.delete(0, tk.END)
        self.target_image.insert(0, default_target_image(distro))

    def _log(self, message: str) -> None:
        self.status.set(message)
        print(message)

    def on_render(self) -> None:
        """Render the Dockerfile without building."""
        self.status.set("Rendering...")
        try:
            dockerfile, image_ref, tags = render(
                self.distro.get(),
                self.tag.get(),
                self.target_image.get(),
            )
        except Exception as exc:
            self._log(f"error: {exc}")
            messagebox.showerror("Render failed", str(exc))
            return
        self._log(f"Rendered {image_ref} ({', '.join(tags)})")
        self._log(f"Dockerfile: {dockerfile}")

    def on_build(self, skip_build: Optional[bool] = None) -> None:
        """Render and optionally build the image in a background thread."""
        overlay = skip_build if skip_build is not None else self.skip_build.get()
        skip_build = overlay == "yes"
        test = skip_build is False and self.test.get() == "yes"
        self.status.set("Rendering...")
        try:
            dockerfile, image_ref, tags = render(
                self.distro.get(),
                self.tag.get(),
                self.target_image.get(),
            )
        except Exception as exc:
            self._log(f"error: {exc}")
            messagebox.showerror("Render failed", str(exc))
            return

        self._log(f"Rendered {image_ref} ({', '.join(tags)})")

        def thread_work() -> None:
            if not skip_build:
                try:
                    self._log("Building...")
                    build_image(dockerfile, image_ref, runtime=self.runtime.get())
                    self._log(f"Built {image_ref}")
                except Exception as exc:
                    self._log(f"error: build failed: {exc}")
                    messagebox.showerror("Build failed", str(exc))
                    return
                if test:
                    try:
                        self._log("Testing...")
                        run_test(image_ref)
                        self._log("Test passed.")
                    except Exception as exc:
                        self._log(f"error: test failed: {exc}")
                        messagebox.showerror("Test failed", str(exc))
                        return

        threading.Thread(target=thread_work, daemon=True).start()
        self.status.set("Done.")


def is_available() -> bool:
    """Return True when tkinter can create its Tk root in this environment."""
    try:
        root = tk.Tk()
    except Exception:
        return False
    root.withdraw()
    root.destroy()
    return True


def main() -> int:
    root = tk.Tk()
    builder = Builder(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
