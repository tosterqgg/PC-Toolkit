import ctypes
import os
import re
import shlex
import shutil
import subprocess
import sys
from time import sleep

import questionary
from alive_progress import alive_bar
from rich import print
from rich.console import Console
from rich.traceback import install

install(show_locals=True)
console = Console()


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def run_as_admin():
    if not is_admin():
        # Pobieramy ścieżkę do interpretera Pythona i aktualnego skryptu
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])

        # Próba ponownego uruchomienia z flagą 'runas' (UAC prompt)
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {params}', None, 1
        )
        sys.exit(0)  # Zamykamy bieżący proces bez uprawnień


def detect_manager():
    possible_managers = ["winget", "scoop", "brew", "apt", "dnf", "pacman"]
    for mgr in possible_managers:
        if shutil.which(mgr) is not None:
            return mgr
    return "Unknown"


def mgr_unknown(pkg_manager):
    if pkg_manager == "Unknown":
        os.system("cls" if os.name == "nt" else "clear")
        mgr_m = questionary.confirm(
            "Unknown package manager detected. Do you want to manually set it?",
            default=True,
        ).ask()
        if mgr_m:
            pkg_manager = questionary.select(
                "Select your package manager:",
                choices=["winget", "scoop", "brew", "apt", "dnf", "pacman"],
            ).ask()
    return pkg_manager  # Musimy zwrócić nową wartość!


def run_with_spinner(cmd, *args):
    title = args[0] if len(args) > 0 else "Przetwarzanie"
    success_msg = args[1] if len(args) > 1 else "Gotowe"

    if isinstance(cmd, str):
        cmd = shlex.split(cmd)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
    )

    last_percent = 0

    with alive_bar(100, title=title, force_tty=True) as bar:
        while True:
            line = process.stdout.readline()  # pyright: ignore[reportOptionalMemberAccess]
            if not line and process.poll() is not None:
                break

            clean_line = line.strip()
            if not clean_line:
                continue

            # Szukamy procentów w linii
            match_pc = re.search(r"(\d+)\s*%", clean_line)
            if match_pc:
                current_percent = int(match_pc.group(1))

                # Jeśli winget raportuje mniejszy procent niż mamy (nowy etap),
                # nie cofamy paska, tylko czekamy aż nas "dogoni" lub ignorujemy spadek
                if current_percent > last_percent:
                    diff = current_percent - last_percent
                    for _ in range(diff):
                        bar()
                    last_percent = current_percent
                elif current_percent < last_percent and last_percent >= 99:
                    # Jeśli byliśmy na końcu i spadło do małej wartości - prawdopodobnie nowy etap
                    # Możemy zresetować last_percent, żeby pasek ruszył od nowa (opcjonalne)
                    pass
            else:
                # Jeśli winget nie sypie procentami, a coś robi, dajemy znać użytkownikowi
                if "Installing" in clean_line or "Starting" in clean_line:
                    # bar.text = clean_line # Jeśli Twoja wersja obsługuje ustawianie tekstu
                    pass

    process.wait()
    if process.returncode == 0:
        print(f"✅ {success_msg}")
    else:
        error_msg = args[2] if len(args) > 2 else "Wystąpił błąd"
        print(f"❌ {error_msg} (Kod: {process.returncode})")


def run_with_spinner_stdout(cmd, *args):
    # Pobieramy argumenty opcjonalne (tytuł, sukces, błąd)
    title = args[0] if len(args) > 0 else "Przetwarzanie"
    success_msg = args[1] if len(args) > 1 else "Gotowe"

    if isinstance(cmd, str):
        cmd = shlex.split(cmd)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
    )

    ignored_chars = {"-", "\\", "|", "/"}

    # Używamy paska (bez konkretnego total, bo winget list nie podaje % postępu)
    with alive_bar(title=title, force_tty=True) as bar:
        while True:
            line = process.stdout.readline()  # pyright: ignore[reportOptionalMemberAccess]
            if not line and process.poll() is not None:
                break

            clean_line = line.strip()
            if not clean_line or clean_line in ignored_chars:
                continue

            # Tutaj kluczowa zmiana: drukujemy KAŻDĄ linię,
            # bo chcemy widzieć listę pakietów
            print(clean_line)
            bar()  # Po prostu animujemy spinner

    process.wait()
    if process.returncode == 0:
        print(f"✅ {success_msg}")
    else:
        error_msg = args[2] if len(args) > 2 else "Wystąpił błąd"
        print(f"❌ {error_msg} (Kod: {process.returncode})")


def ui(pkg_manager):
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        console.print(f"[bold blue]Package Manager: {pkg_manager.upper()}[/bold blue]")

        choice = questionary.select(
            "Select an action:",
            choices=[
                "Install a package",
                "Uninstall a package",
                "Search for a package",
                "Upgrade a package",
                "List installed packages",
                "Info about a package",
                "Useful stuff",
                "Exit",
            ],
        ).ask()

        # Obsługa wyjścia lub Ctrl+C
        if choice == "Exit" or choice is None:
            console.print("[bold yellow]Goodbye![/bold yellow]")
            break

        # --- LOGIKA AKCJI ---
        if choice == "Install a package":
            pkg = questionary.text("What package do you want to install?").ask()
            if pkg:
                cmd = f"winget install {pkg} -e --accept-source-agreements --accept-package-agreements"
                run_with_spinner(
                    cmd,
                    f"Installing {pkg}",
                    f"✓ Success: {pkg} installed.",
                    f"✗ Error: Could not install {pkg}.",
                )

        elif choice == "Uninstall a package":
            pkg = questionary.text("What package do you want to uninstall?").ask()
            if pkg:
                run_with_spinner(
                    f"winget uninstall {pkg} -e",
                    f"Uninstalling {pkg}",
                    f"✓ Success: {pkg} uninstalled.",
                    f"✗ Error: Could not uninstall {pkg}.",
                )

        elif choice == "Search for a package":
            pkg = questionary.text("What package do you want to search for?").ask()
            if pkg:
                run_with_spinner_stdout(
                    f"winget search {pkg}",
                    f"Searching for {pkg}",
                    "✓ Search completed.",
                    f"✗ Error: Could not search for {pkg}.",
                )

        elif choice == "Upgrade a package":
            pkg = questionary.text("What package do you want to upgrade?").ask()
            if pkg:
                run_with_spinner(
                    f"winget upgrade {pkg} -e",
                    f"Upgrading {pkg}",
                    f"✓ Success: {pkg} upgraded.",
                    f"✗ Error: Could not upgrade {pkg}.",
                )

        elif choice == "List installed packages":
            run_with_spinner_stdout(
                "winget list",
                "Listing installed packages",
                "✓ List completed:\n",
                "✗ Error: Could not list installed packages.",
            )

        elif choice == "Info about a package":
            pkg = questionary.text("What package do you want info about?").ask()
            if pkg:
                run_with_spinner_stdout(
                    f"winget show {pkg}",
                    f"Getting info about {pkg}",
                    "✓ Info retrieved:\n",
                    f"✗ Error: Could not get info about {pkg}.",
                )

        elif choice == "Useful stuff":
            choice_useful = questionary.select(
                "Select an action:", choices=["System repair", "Back"]
            ).ask()

            if choice_useful == "System repair":
                run_with_spinner(
                    "sfc /scannow",
                    "Running system repair (sfc /scannow)",
                    "✓ System repair completed.",
                    "✗ Error: System repair failed.",
                )

            elif choice_useful == "Back":
                continue  # Wraca na początek pętli natychmiast

        # --- TWÓJ NOWY POTWIERDZACZ ---
        # Wyświetla się po każdej akcji (z wyjątkiem 'Back', bo tam daliśmy 'continue')
        go_back = questionary.confirm(
            "Do you want to return to the main menu?", default=True
        ).ask()

        if not go_back:
            console.print("[bold yellow]Goodbye![/bold yellow]")
            break

    sys.exit(0)


# --- URUCHOMIENIE ---
if not is_admin():
    console.print(
        "[yellow]System repair requires admin privileges. Restarting...[/yellow]"
    )
    sleep(2)
    run_as_admin()
current_mgr = detect_manager()
current_mgr = mgr_unknown(current_mgr)
ui(current_mgr)
