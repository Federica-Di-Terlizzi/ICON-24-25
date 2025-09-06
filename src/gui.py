import tkinter as tk
from tkinter import ttk, messagebox
from typing import cast
from tkinter import PhotoImage
from PIL import Image, ImageTk, ImageSequence
import threading
import requests
from io import BytesIO
from itinerario import (fetch_monuments_by_qid, plan_itinerary_by_popularity, find_city_candidates)
from typing import Optional
import re
import unicodedata


def load_image_from_url(url: str, size=(120, 120)):
    print(f"Tentativo di caricamento immagine da URL: {url}")
    headers = {
        "User-Agent": "TRIPlanner/1.0 (offline educational use)"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        img = img.resize(size, Image.Resampling.LANCZOS)
        return cast(PhotoImage, ImageTk.PhotoImage(img))
    except Exception as e:
        messagebox.showerror("⚠️", f"Errore nel caricamento immagine:{e}")
        return None


def load_placeholder_image(size=(120, 120)):
    try:
        img = Image.open("assets/placeholder.png").resize(size, Image.Resampling.LANCZOS)
        return cast(PhotoImage, ImageTk.PhotoImage(img))
    except Exception as e:
        return e


def normalize_city_name(name: str) -> str:
    name = unicodedata.normalize('NFKC', name)
    name = name.strip().lower()
    return name


class StartPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="white")
        self.controller = controller
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = tk.Frame(self, bg="white")
        container.grid(row=0, column=0, sticky="nsew")

        tk.Label(container, text="TRIPlanner", font=("Helvetica", 36, "bold"), bg="white").pack(pady=10)

        try:
            self.globe_gif = Image.open("assets/globe.gif")
            self.frames_gif = [ImageTk.PhotoImage(img.resize((250, 250), Image.Resampling.LANCZOS))
                               for img in ImageSequence.Iterator(self.globe_gif)]
            self.globe_lbl = tk.Label(container, bg="white")
            self.globe_lbl.pack(pady=10)
            self._animate()
        except FileNotFoundError:
            # File mancante: mostra solo il titolo senza animazione
            self.globe_lbl = tk.Label(container, text="TRIPlanner", font=("Helvetica", 24), bg="white")
            self.globe_lbl.pack(pady=10)
            messagebox.showerror("⚠️", f"assets/globe.gif non trovato, salto animazione")

        ttk.Button(container, text="Inizia il viaggio",
                   command=lambda: controller.show_frame("InputPage")).pack(pady=20)

    def _animate(self, idx=0):
        frame = self.frames_gif[idx]
        self.globe_lbl.configure(image=cast(PhotoImage, frame))
        self.globe_lbl.image = frame
        self.after(100, self._animate, (idx + 1) % len(self.frames_gif))


class InputPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#5f95b2")
        self.controller = controller
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.selected_qid = None
        self.selected_city_name = None
        self._city_selection_active = False
        self._city_lookup_active = False

        container = tk.Frame(self, bg="#3cb371")
        container.grid(row=0, column=0, sticky="nsew", padx=50, pady=30)

        tk.Label(container, text="Organizza il tuo viaggio",
                 font=("Helvetica", 20, "bold"), bg="#3cb371", fg="white").pack(fill="x", pady=(0, 20))

        form = tk.Frame(container, bg="#3cb371")
        form.pack(fill="both", expand=True)

        tk.Label(form, text="Nome città:", font=("Helvetica", 14, "bold"),
                 bg="#3cb371", fg="white").grid(row=0, column=0, sticky="w", pady=10)
        tk.Label(form, text="Numero giorni di soggiorno:", font=("Helvetica", 14, "bold"),
                 bg="#3cb371", fg="white").grid(row=1, column=0, sticky="w", pady=10)

        self.city_entry = ttk.Entry(form, width=30)
        self.city_entry.grid(row=0, column=1, padx=10, pady=10)
        self._typing_timer = None
        self._last_city_input = ""
        self.days_entry = ttk.Entry(form, width=10)
        self.days_entry.config(state="disabled")
        self.days_entry.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        ttk.Button(container, text="Crea itinerario", command=self._on_create).pack(pady=20)

    def _run_city_lookup_thread(self, city):
        try:
            normalized_city = normalize_city_name(city)
            candidates = find_city_candidates(normalized_city)
        except Exception as e:
            self._close_loading_popup()
            messagebox.showerror("⚠️", f"Errore nella ricerca città: {e}")
            candidates = []

        self._close_loading_popup()

        def update_ui(candidates_local):
            self._city_lookup_active = False
            if not candidates_local:
                self._enable_create_button()
                messagebox.showerror("⚠️", "Nessuna città trovata.")
                return

            if len(candidates_local) == 1:
                self.selected_qid = candidates_local[0]["qid"]
                self.selected_city_name = candidates_local[0]["label"]
                self.controller.city = self.selected_city_name
                self.controller.days = self.temp_days
                self.controller.show_frame("LoadingPage")
                self.after(100, lambda: self.controller.fetch_and_generate_from_qid(self.selected_qid))
            else:
                self._ask_city_selection(candidates_local)

        self.after(0, lambda: update_ui(candidates))

    def _on_create(self):
        if self._city_lookup_active:
            return  # Evita chiamate multiple

        city = self.city_entry.get().strip()
        if not city or city.isdigit():
            messagebox.showerror("Input errato", "Inserisci un nome città valido.")
            return

        if not re.match(r'^[a-zA-ZÀ-ÿ\s]+$', city):
            messagebox.showerror("Input errato", "Il nome della città deve contenere solo lettere.")
            return

        days = self._get_valid_days()
        if days is None:
            messagebox.showerror("Input errato", "Inserisci un numero di giorni valido (≥1).")
            return

        self.temp_days = days

        self._disable_create_button()

        if self.selected_qid:
            self.controller.city = self.selected_city_name
            self.controller.days = days
            self.controller.show_frame("LoadingPage")
            self.after(100, lambda: self.controller.fetch_and_generate_from_qid(self.selected_qid))
        else:
            self._city_lookup_active = True
            self._show_loading_popup("Sto cercando la città...")
            threading.Thread(target=self._run_city_lookup_thread, args=(city,), daemon=True).start()

    def _disable_create_button(self):
        for widget in self.winfo_children():
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button) and child.cget("text") == "Crea itinerario":
                    child.config(state="disabled")

    def _enable_create_button(self):
        for widget in self.winfo_children():
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button) and child.cget("text") == "Crea itinerario":
                    child.config(state="normal")

    def _fetch_then_enable(self, qid):
        self.controller.fetch_and_generate_from_qid(qid)
        self._enable_create_button()

    def on_show(self):
        self.city_entry.delete(0, tk.END)
        self.days_entry.delete(0, tk.END)
        self.days_entry.config(state="normal")
        self.selected_qid = None
        self.selected_city_name = None
        self._last_city_input = ""
        self._city_selection_active = False
        self._city_lookup_active = False
        self._enable_create_button()

    def _ask_city_selection(self, city_options):
        win = tk.Toplevel(self)
        win.title("Seleziona la città corretta")
        win.transient(self.controller)
        win.lift()
        self.icon_image = tk.PhotoImage(file="assets/plane_icon.png")
        win.iconphoto(False, self.icon_image)

        self._center_popup(win, 400, 200)
        self.controller.bind("<Configure>", lambda e: self.safe_center_popup(win, 400, 200))

        tk.Label(win, text="Seleziona la città desiderata:", font=("Helvetica", 12)).pack(pady=10)

        unique_options = []
        seen_display = set()
        for opt in city_options:
            label = opt.get("label") or self.city_entry.get().strip().title()
            country = opt.get("country") or "Paese sconosciuto"
            display_str = f"{label} ({country})"
            if display_str not in seen_display:
                seen_display.add(display_str)
                opt["label"] = label
                opt["country"] = country
                unique_options.append(opt)

        value_to_option = {
            f'{opt["label"]} ({opt["country"]})': opt
            for opt in unique_options
        }

        combo = ttk.Combobox(win, state="readonly", values=list(value_to_option.keys()))
        combo.pack(pady=10)
        combo.current(0)

        def confirm():
            selected_label = combo.get()
            selected_option = value_to_option.get(selected_label)

            if not selected_option:
                messagebox.showerror("⚠️", "Errore nella selezione della città.")
                win.destroy()
                return

            qid = selected_option["qid"]
            name = selected_option["label"]
            win.destroy()
            self.selected_qid = qid
            self.selected_city_name = name
            self.controller.city = name
            self.controller.days = self.temp_days
            self.controller.show_frame("LoadingPage")
            self.after(100, lambda: self.controller.fetch_and_generate_from_qid(qid))

        def on_close():
            self._enable_create_button()
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)

        ttk.Button(win, text="Conferma", command=confirm).pack(pady=10)

    def _get_valid_days(self) -> Optional[int]:
        days_txt = self.days_entry.get().strip()
        if not days_txt.isdigit() or int(days_txt) < 1:
            return None
        return int(days_txt)

    def _show_loading_popup(self, message="Sto cercando la città..."):
        width, height = 300, 100
        self.loading_popup = tk.Toplevel(self)
        self.loading_popup.resizable(False, False)
        self.loading_popup.transient(self.controller)
        self.loading_popup.lift()
        self.icon_image = tk.PhotoImage(file="assets/plane_icon.png")
        self.loading_popup.iconphoto(False, self.icon_image)
        self._center_popup(self.loading_popup, width, height)

        self.controller.bind("<Configure>", lambda e: self.safe_center_popup(self.loading_popup, width, height))
        tk.Label(self.loading_popup, text=message, font=("Helvetica", 12)).pack(expand=True, pady=20)
        self._disable_inputs()

        def on_close():
            self._enable_create_button()
            self._city_lookup_active = False
            self._enable_inputs()
            self.loading_popup.destroy()

        self.loading_popup.protocol("WM_DELETE_WINDOW", on_close)
        self.loading_popup.update()

    def _disable_inputs(self):
        self.city_entry.config(state="disabled")
        self.days_entry.config(state="disabled")

    def _enable_inputs(self):
        self.city_entry.config(state="normal")
        self.days_entry.config(state="normal")

    def _close_loading_popup(self):
        if hasattr(self, "loading_popup") and self.loading_popup.winfo_exists():
            self.loading_popup.destroy()
            self._enable_inputs()

    def _center_popup(self, popup, width, height):
        self.controller.update_idletasks()
        root_x = self.controller.winfo_rootx()
        root_y = self.controller.winfo_rooty()
        root_w = self.controller.winfo_width()
        root_h = self.controller.winfo_height()
        x = root_x + (root_w // 2) - (width // 2)
        y = root_y + (root_h // 2) - (height // 2)
        popup.geometry(f"{width}x{height}+{x}+{y}")

    def safe_center_popup(self, popup, width, height):
        if popup and popup.winfo_exists():
            self._center_popup(popup, width, height)


class LoadingPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#5f95b2")
        self.controller = controller
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = tk.Frame(self, bg="#5f95b2")
        container.grid(row=0, column=0, sticky="nsew")

        tk.Label(container, text="Caricamento...", font=("Helvetica", 24, "bold"),
                 bg="#5f95b2", fg="white").pack(pady=50)
        self.bar = ttk.Progressbar(container, mode="indeterminate", length=400)
        self.bar.pack(pady=20)

    def on_show(self):
        self.bar.start(10)


class ResultPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#3cb371")
        self.controller = controller
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, minsize=50)
        self.grid_columnconfigure(0, weight=1)

        main_container = tk.Frame(self, bg="#3cb371")
        main_container.grid(row=0, column=0, sticky="nsew")

        self.canvas = tk.Canvas(main_container, bg="#3cb371")
        self.scroll_y = ttk.Scrollbar(main_container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll_y.set)

        self.scroll_y.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.frame = tk.Frame(self.canvas, bg="#3cb371")
        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.bottom_btn_frame = tk.Frame(self, bg="#5f95b2")
        self.bottom_btn_frame.grid(row=1, column=0, sticky="nsew")
        self.bottom_btn_frame.grid_columnconfigure(0, weight=1)

        self.back_btn = ttk.Button(self.bottom_btn_frame, text="Torna indietro",
                                   command=lambda: self.controller.show_frame("InputPage"))
        self.back_btn.pack(expand=True)

    def on_show(self):
        for child in self.frame.winfo_children():
            child.destroy()

        data = self.controller.itinerary_data or []

        for idx, monuments in enumerate(data, start=1):
            title = f"Giorno {idx}:"
            tk.Label(self.frame, text=title, font=("Helvetica", 20, "bold"), bg="#3cb371") \
                .pack(anchor="w", padx=30, pady=(20, 5))

            if not monuments:
                tk.Label(self.frame, text="Nessun risultato trovato.",
                         font=("Helvetica", 12, "italic"), bg="#3cb371", fg="gray").pack(anchor="w", padx=50,
                                                                                         pady=(0, 10))
                continue

            for monument in monuments:
                name = monument.get("label", "Sconosciuto")
                img_url = monument.get("image")

                row = tk.Frame(self.frame, bg="#3cb371")
                row.pack(fill="x", padx=50, pady=10)

                image = load_image_from_url(img_url) if img_url else None
                if not image:
                    image = load_placeholder_image()

                image_label = tk.Label(row, image=image, bg="#3cb371", width=120, height=120)
                image_label.image = image
                image_label.pack(side="left", padx=(0, 15))

                details = tk.Frame(row, bg="#3cb371")
                details.pack(side="left", fill="both", expand=True)

                tk.Label(details, text=name, font=("Helvetica", 14, "bold"), bg="#3cb371").pack(anchor="w")

                desc = monument.get("description", "Descrizione non disponibile.")
                tk.Label(details, text=desc, wraplength=600, justify="left", bg="#3cb371", font=("Helvetica", 11)) \
                    .pack(anchor="w", pady=(5, 0))


class TriPlannerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TRIPlanner")
        self.iconphoto(False, tk.PhotoImage(file="assets/plane_icon.png"))
        self.geometry("900x600")
        self.minsize(600, 450)
        self.city = None
        self.days = None
        self.itinerary_data = None

        self._container = tk.Frame(self)
        self._container.pack(fill="both", expand=True)
        self._container.grid_rowconfigure(0, weight=1)
        self._container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (StartPage, InputPage, LoadingPage, ResultPage):
            frame = F(parent=self._container, controller=self)
            self.frames[F.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("StartPage")

    def show_frame(self, name):
        frame = self.frames[name]
        frame.tkraise()
        if hasattr(frame, "on_show"):
            frame.on_show()

    def start_itinerary(self, city, days):
        self.city = city
        self.days = days
        self.show_frame("LoadingPage")
        threading.Thread(target=self._generate_itinerary, daemon=True).start()

    def _generate_itinerary(self):
        try:
            candidates = find_city_candidates(self.city)
            if not candidates:
                raise ValueError("Nessuna città trovata.")
            self.fetch_and_generate_from_qid(candidates[0]["qid"])
        except Exception as e:
            messagebox.showerror("⚠️", f"Errore nel recupero città:{e}")
            self.itinerary_data = [[] for _ in range(self.days)]
            self.show_frame("ResultPage")

    def fetch_and_generate_from_qid(self, qid):
        def worker():
            try:
                monuments = fetch_monuments_by_qid(qid, limit=60)
                self.itinerary_data = plan_itinerary_by_popularity(monuments, self.days)
            except Exception as e:
                messagebox.showerror("⚠️", f"Errore nel fetch dei monumenti:{e}")
                self.itinerary_data = [[] for _ in range(self.days)]
            finally:
                self.after(0, lambda: self.show_frame("ResultPage"))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = TriPlannerApp()
    app.mainloop()
