# Description: This script downloads the latest MTA Server nightly build for the current OS and architecture,
# extracts the server files and updates the server binaries in the specified folder.
#
# Author: Fernando
# Version: 1.2
# Last updated: 2024-10-10

try:
    import os
    import platform
    import sys
    import subprocess
    import requests
    import shutil
    import traceback
    import tarfile
    from bs4 import BeautifulSoup
    import datetime
except ImportError as e:
    print("You are missing the following module(s):", e.name)
    exit(1)

OS_SYSTEM = platform.system() # e.g. Windows, Linux
IS_64_BIT = sys.maxsize > 2**32 # True if 64-bit, False if 32-bit
IS_ARM = platform.machine().startswith('arm') # True if ARM, False otherwise

# Downloaded build archives vary depending on the architecture and OS
BUILD_STRINGS = {
    "arm": {
        "Windows": {
            "64": "Windows arm64 server",
            "32": False
        },
        "Linux": {
            "64": "Linux arm64 server",
            "32": "Linux arm server"
        }
    },
    "x86": {
        "Windows": {
            "64": "Windows 64 bit server",
            "32": "Windows nightly installer (Win10+)"
        },
        "Linux": {
            "64": "Linux 64 bit server",
            "32": "Linux 32 bit server"
        }
    }
}

cpu_arch = "arm" if IS_ARM else "x86"
os_name = "Windows" if OS_SYSTEM == "Windows" else "Linux"
cpu_bits = "64" if IS_64_BIT else "32"

BUILD_STRING = BUILD_STRINGS[cpu_arch][os_name][cpu_bits]
if not BUILD_STRING:
    print(f"This script is not compatible with your system ({os_name} {cpu_bits} bit).")
    exit(1)

EXEC_FILE_NAMES = {
    "arm": {
        "Windows": {
            "64": "MTA Server ARM64.exe",
        },
        "Linux": {
            "64": "mta-server-arm64",
            "32": "mta-server-arm"
        }
    },
    "x86": {
        "Windows": {
            "64": "MTA Server64.exe",
            "32": "MTA Server.exe"
        },
        "Linux": {
            "64": "mta-server64",
            "32": "mta-server"
        }
    }
}
EXEC_FILE_NAME = EXEC_FILE_NAMES[cpu_arch][os_name][cpu_bits]

SERVER_BINARIES_LOCATIONS = {
    "arm": {
        "Windows": {
            "64": "arm64",
        },
        "Linux": {
            "64": "arm64",
            "32": "arm",
        }
    },
    "x86": {
        "Windows": {
            "64": "x64",
            "32": "./",
        },
        "Linux": {
            "64": "x64",
            "32": "./",
        }
    }
}
SERVER_BINARIES_LOCATION = SERVER_BINARIES_LOCATIONS[cpu_arch][os_name][cpu_bits]

def ask_for_server_folder():
    server_folder = input("\nEnter the server folder path, where MTA Server 64.exe is (leave empty to use current folder): ")
    if not server_folder:
        server_folder = os.getcwd()

    if not os.path.exists(server_folder):
        print("That folder path does not exist.")
        exit(1)

    server_exe = os.path.join(server_folder, EXEC_FILE_NAME)
    if not os.path.exists(server_exe):
        print(f"\n{EXEC_FILE_NAME} not found in the specified folder. Are you sure you specified the right folder?")
        if input("   Type 'yes' to continue: ").lower() != 'yes':
            exit(0)
    return server_folder

def fetch_exe_url():
    nightly_url = "https://nightly.multitheftauto.com/"
    response = requests.get(nightly_url)
    if response.status_code != 200:
        print(f"Error fetching the nightly builds page: Website responded with code {response.status_code}")
        exit(1)
    
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find the td element with the text
    td = soup.find('td', string=BUILD_STRING)
    # Find table after the td element
    table = td.find_next('table')
    # Find the first tr in the table with class file and without display: none
    tr = table.find('tr', class_='file', style=lambda x: x is None)
    # Find the first a element in the tr
    a = tr.find('a')
    # Get the href attribute of the a element
    href = a['href']

    final_url = f"{nightly_url}{href}"

    print(f"\nLatest nightly build found: {BUILD_STRING} @ {final_url}")
    return final_url

def prepare_updateinfo_folder(server_folder):
    updateinfo_folder = os.path.join(server_folder, 'updateinfo')
    if not os.path.exists(updateinfo_folder):
        os.makedirs(updateinfo_folder)
    return updateinfo_folder

def download_file(url, dest_folder):
    local_filename = os.path.join(dest_folder, url.split('/')[-1])
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return local_filename

def extract_files(file_path, dest_folder):
    if file_path.endswith(".exe"):
        # Check if 7z is in PATH
        if shutil.which('7z') is None:
            print("7z is required to extract the downloaded file. Please install 7z and add it to PATH.")
            exit(1)
        # Extract only the "server" folder
        command = ['7z', 'x', file_path, 'server/*', f'-o{dest_folder}', '-y']
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    elif file_path.endswith(".tar.gz"):
        # File contains a .tar inside, which then contains a single folder with the files we want
        with tarfile.open(file_path, 'r:gz') as tar:
            tar.extractall(dest_folder)
        # Rename the single folder extracted to 'server'
        extracted_folder = os.path.join(dest_folder, os.listdir(dest_folder)[0])
        os.rename(extracted_folder, os.path.join(dest_folder, 'server'))
    else:
        print(f"Unsupported file format: {file_path}")
        exit(1)

def update_server(updateinfo_folder, server_folder):
    source_folder = os.path.join(updateinfo_folder, 'server')
    binaries_folder = os.path.join(source_folder, SERVER_BINARIES_LOCATION)
    server_exe = os.path.join(source_folder, EXEC_FILE_NAME)

    # Copy DLL/SO files
    dest_binaries_folder = os.path.join(server_folder, SERVER_BINARIES_LOCATION)
    for root, dirs, files in os.walk(binaries_folder):
        for file in files:
            # only files that end in .dll or .so
            if not file.endswith(('.dll', '.so')):
                continue
            src_file = os.path.join(root, file)
            dest_file = os.path.join(dest_binaries_folder, os.path.relpath(src_file, binaries_folder))
            if not os.path.exists(os.path.dirname(dest_file)):
                os.makedirs(os.path.dirname(dest_file))
            shutil.copy2(src_file, dest_file)
    
    # Copy MTA server executable file
    dest_server_exe = os.path.join(server_folder, EXEC_FILE_NAME)
    if os.path.exists(dest_server_exe):
        os.remove(dest_server_exe)
    shutil.copy2(server_exe, dest_server_exe)

def log_update(server_folder, url):
    file_from_url = url.split('/')[-1]
    log_filename = "updates.log"
    log_file = os.path.join(server_folder, log_filename)
    today_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, 'a') as f:
        f.write(f"{today_date} - Server updated with {file_from_url} | Python MTA Server Updater\n")

def delete_folder(folder):
    if os.path.exists(folder) and os.path.isdir(folder):
        shutil.rmtree(folder)

def clear_folder(folder):
    if os.path.exists(folder) and os.path.isdir(folder):
        for root, dirs, files in os.walk(folder):
            for file in files:
                os.remove(os.path.join(root, file))

if __name__ == "__main__":
    try:
        
        print("\n---- MTA Server Updater by Fernando ----")
        print(f"\nOS: {OS_SYSTEM} | 64-bit: {IS_64_BIT} | ARM: {IS_ARM}")
        
        args = sys.argv[1:]
        provided_server_folder = args[0] if args else None
        if provided_server_folder:
            if not os.path.exists(provided_server_folder):
                print(f"The provided server folder path does not exist: {provided_server_folder}")
                exit(1)
            server_folder = provided_server_folder
            print(f"\nUsing provided server folder: {server_folder}")
        else:
            server_folder = ask_for_server_folder()
        
        print("\nBeginning the update process...")

        url = fetch_exe_url()
        
        updateinfo_folder = prepare_updateinfo_folder(server_folder)
        clear_folder(updateinfo_folder)

        print("\nDownloading file...")
        downloaded_file = download_file(url, updateinfo_folder)

        print("\nExtracting the downloaded file...")
        extract_files(downloaded_file, updateinfo_folder)

        update_server(updateinfo_folder, server_folder)

        log_update(server_folder, url)

        delete_folder(updateinfo_folder)

        print("\nServer binaries were successfully updated. Bye!\n")

    except Exception as e:
        print(traceback.format_exc())
