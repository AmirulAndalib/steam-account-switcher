import tkinter as tk
import tkinter.ttk as ttk
import traceback
from tkinter.scrolledtext import ScrolledText
from tkinter import messagebox as msgbox
import gettext
import os
import queue as q
import requests as req
import zipfile as zf
import sys
import threading
import logging
from time import sleep
from packaging import version
from ruamel.yaml import YAML
from pget.down import Downloader
from modules.config import config_manager as cm
from modules.errormsg import error_msg
from modules.ui import get_color

logger = logging.getLogger(__name__)
yaml = YAML()

LOCALE = cm.get('locale')

t = gettext.translation('steamswitcher',
                        localedir='locale',
                        languages=[LOCALE],
                        fallback=True)
_ = t.gettext

update_frame = None
bundled = True


class RatelimitedException(BaseException):
    pass


#  Update code is a real mess right now. You have been warned.


def start_checkupdate(master, cl_ver_str, bundle, debug=False, **kw):
    '''Check if application has update'''
    global update_frame
    global update_label
    global bundled

    try:
        exception = kw['exception']
    except KeyError:
        exception = False

    if update_frame is not None:
        update_frame.destroy()

    update_label = tk.Label(master)
    update_frame = tk.Frame(master)
    update_frame.config(bg=get_color('bottomframe'))

    if not bundle and not debug:
        tk.Frame(update_frame, bg='grey').pack(fill='x')
        update_frame.pack(side='bottom', fill='x')
        bundled = False
        master.update()
        return
    else:
        update_frame.pack(side='bottom', fill='x')

    tk.Frame(update_frame, bg='grey').pack(fill='x')
    master.update()

    def update(sv_version, changelog, zip_url):
        nonlocal debug

        updatewindow = tk.Toplevel(master)
        updatewindow.title(_('Update'))
        updatewindow.geometry(master.popup_geometry(400, 300))
        updatewindow.resizable(False, False)
        updatewindow.focus()

        try:
            updatewindow.iconbitmap('asset/icon.ico')
        except tk.TclError:
            pass

        button_frame = tk.Frame(updatewindow)
        button_frame.pack(side=tk.BOTTOM, pady=3)

        cancel_button = ttk.Button(button_frame, text=_('Cancel'),
                                   command=updatewindow.destroy)
        update_button = ttk.Button(button_frame, text=_('Update now'), style='Accent.TButton')

        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)

        text_frame = tk.Frame(updatewindow)
        text_frame.pack(side=tk.TOP, pady=3)
        text = tk.Label(text_frame,
                        text=_('New version %s is available.') % sv_version)
        text.pack()

        changelog_box = ScrolledText(updatewindow, width=57, relief='solid', bd=0)
        changelog_box.insert(tk.CURRENT, changelog)
        changelog_box.configure(state=tk.DISABLED)
        changelog_box.pack(padx=5)

        updatewindow.grab_set()

        def start_update():
            '''Withdraw main window and start update download'''
            nonlocal button_frame
            nonlocal cancel_button
            nonlocal update_button
            nonlocal debug
            nonlocal sv_version
            nonlocal updatewindow

            master.withdraw()
            try:
                os.remove('update.zip')
            except OSError:
                if os.path.isfile('update.zip'):
                    msgbox.showerror(_('Error'),
                                     _("Couldn't delete existing update file.\nPlease delete it manually and try again."))
                    updatewindow.destroy()
                    master.deiconify()
                    return

            install = True

            # For development purposes
            if not bundle and debug:
                if not msgbox.askyesno('', 'Install update?'):
                    install = False

            cancel_button.destroy()
            update_button.destroy()

            def cancel():
                if msgbox.askokcancel(_('Cancel'), _('Are you sure to cancel?')):
                    downloader.stop()
                    updatewindow.destroy()
                    master.deiconify()
                    return

            # There's no cancel button so we use close button as one instead
            updatewindow.protocol("WM_DELETE_WINDOW", cancel)

            # Define progress variables
            dl_p = tk.IntVar()
            dl_p.set(0)
            dl_pbar = ttk.Progressbar(button_frame,
                                      length=150,
                                      orient=tk.HORIZONTAL,
                                      variable=dl_p)
            dl_pbar.pack(side='left', padx=5)

            dl_prog_var = tk.StringVar()
            dl_prog_var.set('-------- / --------')
            dl_prog = tk.Label(button_frame, textvariable=dl_prog_var)

            dl_speed_var = tk.StringVar()
            dl_speed_var.set('---------')
            dl_speed = tk.Label(button_frame, textvariable=dl_speed_var)

            dl_prog.pack(side='right', padx=5)
            dl_speed.pack(side='right', padx=5)
            master.update()

            try:
                r = req.get(zip_url, stream=True)
                r.raise_for_status()
                total_size = int(r.headers.get('content-length'))
                total_in_MB = round(total_size / 1048576, 1)
            except req.RequestException:
                msgbox.showerror(_('Error'),
                                 _('Error occured while downloading update.') + '\n\n' + traceback.format_exc())
                updatewindow.destroy()
                master.deiconify()
                return

            if round(total_in_MB, 1).is_integer():
                total_in_MB = int(total_in_MB)

            def launch_updater():
                if not install:
                    return

                while not os.path.isfile('update.zip'):
                    sleep(1)

                try:
                    archive = os.path.join(os.getcwd(), 'update.zip')

                    f = zf.ZipFile(archive, mode='r')
                    f.extractall(members=(member for member in f.namelist() if 'updater' in member))

                    os.execv('updater/updater.exe', sys.argv)
                except (FileNotFoundError, zf.BadZipfile, OSError):
                    error_msg(_('Error'), _("Couldn't perform automatic update.") + '\n' +
                              _('Update manually by extracting update.zip file.'))

            def dl_callback(downloader):
                nonlocal total_in_MB

                current_size = downloader.total_downloaded
                current_in_MB = round(current_size / 1048576, 1)

                if round(current_in_MB, 1).is_integer():
                    current_in_MB = int(current_in_MB)

                perc = int(current_size / total_size * 100)
                prog = f'{current_in_MB}MB / {total_in_MB}MB'

                dl_p.set(perc)
                dl_prog_var.set(prog)
                dl_speed_var.set(downloader.readable_speed + '/s')
                master.update()

                if perc == 100 and downloader.total_merged == downloader.total_length:
                    launch_updater()

            downloader = Downloader(zip_url, 'update.zip', 8)
            downloader.subscribe(dl_callback)
            downloader.start()

        update_button['command'] = lambda: start_update()
        cancel_button.grid(row=0, column=0, padx=(0, 3))
        update_button.grid(row=0, column=1)

    queue = q.Queue()

    def checkupdate():
        '''Fetch version information from GitHub and
        return different update codes'''
        logger.info('Update check start')
        update = None
        try:
            if exception:
                raise req.RequestException
            with req.get('https://api.github.com/repos/sw2719/steam-account-switcher/releases') as r:
                if r.status_code == 403:
                    raise RatelimitedException
                data = r.json()

                for release in data:
                    if not release['prerelease']:
                        latest = release
                        break

                latest_version = latest['tag_name'].replace('v', '')
                latest_zip = latest['assets'][0]['browser_download_url']
                latest_changelog = latest['body'].replace('\r', '').split('# ')

                print(latest_changelog)

                # ['', en, ko]
                if cm.get('locale') == 'ko_KR':
                    latest_changelog = latest_changelog[2].replace('변경사항\n', '')
                else:
                    latest_changelog = latest_changelog[1].replace('Changelogs\n', '')

            logger.info(f'Latest version is {latest_version}')
            logger.info(f'Program version is {cl_ver_str}')

            latest = version.parse(latest_version)
            current = version.parse(cl_ver_str)

            if latest > current:
                update = 'avail'
            elif latest == current:
                update = 'latest'
            elif latest < current:
                update = 'dev'

        except (req.RequestException, req.ConnectionError,
                req.Timeout, req.ConnectTimeout):
            update = 'error'
            sv_version_str = '0'
            changelog = None

        except RatelimitedException:
            update = 'ratelimited'
            sv_version_str = '0'
            changelog = None

        queue.put((update, latest_version, latest_changelog, latest_zip))

    update_code = None
    sv_version = None
    changelog = None

    def get_output():
        '''Get version info from checkupdate() and draw UI accordingly.'''
        global update_frame
        global update_label
        global update_code

        nonlocal sv_version
        nonlocal changelog
        nonlocal debug
        try:
            v = queue.get_nowait()
            update_code = v[0]
            sv_version = v[1]
            changelog = v[2]
            zip_url = v[3]

            if debug:
                logger.info('Update debug mode')

                update_frame.destroy()

                update_frame = tk.Frame(master, bg=get_color('bottomframe'))
                tk.Frame(update_frame).pack(fill='x', pady=(0, 2))
                tk.Frame(update_frame, bg='grey').pack(fill='x')
                update_frame.pack(side='bottom', fill='x')

                update_label = tk.Label(update_frame, bg=get_color('bottomframe'),
                                        text=f'Client: {cl_ver_str} / Server: {sv_version} / {update_code} / Click to open UI')
                update_label.pack(side='bottom')

                update_label.bind('<ButtonRelease-1>', lambda event: update(sv_version=sv_version,
                                                                            changelog=changelog,
                                                                            zip_url=zip_url))

                update_frame.bind('<ButtonRelease-1>', lambda event: update(sv_version=sv_version,
                                                                            changelog=changelog,
                                                                            zip_url=zip_url))
                return

            if update_code == 'avail':
                logger.info('Update Available')

                update_frame.destroy()

                update_frame = tk.Frame(master, bg=get_color('bottomframe'))
                tk.Frame(update_frame, bg='grey').pack(fill='x', pady=(0, 2))
                update_frame.pack(side='bottom', fill='x')

                update_label = tk.Label(update_frame,
                                        text=_('Version %s is available. Click here to update!') % sv_version,
                                        bg=get_color('bottomframe'),
                                        fg=get_color('autologin_text_avail'))
                update_label.pack(side='bottom')
                update_label.bind('<ButtonRelease-1>',
                                  lambda event: update(sv_version=sv_version, changelog=changelog, zip_url=zip_url))
                update_frame.bind('<ButtonRelease-1>',
                                  lambda event: update(sv_version=sv_version, changelog=changelog, zip_url=zip_url))
            elif update_code == 'latest':
                logger.info('On latest version')

                update_frame.destroy()

                update_frame = tk.Frame(master, bg=get_color('bottomframe'))
                tk.Frame(update_frame, bg='grey').pack(fill='x')
                update_frame.pack(side='bottom', fill='x')
            elif update_code == 'dev':
                logger.info('Development version')

                update_frame.destroy()

                update_frame = tk.Frame(master, bg=get_color('bottomframe'))
                tk.Frame(update_frame, bg='grey').pack(fill='x', pady=(0, 2))
                update_frame.pack(side='bottom', fill='x')

                update_label = tk.Label(update_frame,
                                        text=_('Development version'),
                                        bg=get_color('bottomframe'),
                                        fg=get_color('text'))
                update_label.pack(side='bottom')
            elif update_code == 'error':
                logger.info('Exception while checking for updates')

                update_frame.destroy()

                update_frame = tk.Frame(master, bg=get_color('bottomframe'))
                tk.Frame(update_frame, bg='grey').pack(fill='x', pady=(0, 2))
                update_frame.pack(side='bottom', fill='x')

                update_label = tk.Label(update_frame,
                                        text=_('Failed checking for updates. Click here to try again.'),
                                        bg=get_color('bottomframe'),
                                        fg=get_color('autologin_text_unavail'))
                update_frame.bind('<ButtonRelease-1>', lambda event: start_checkupdate(master, cl_ver_str, bundle, debug=debug))
                update_label.bind('<ButtonRelease-1>', lambda event: start_checkupdate(master, cl_ver_str, bundle, debug=debug))
                update_label.pack(side='bottom')
            elif update_code == 'ratelimited':
                logger.info('GitHub API rate limit exceeded')

                update_frame.destroy()

                update_frame = tk.Frame(master, bg=get_color('bottomframe'))
                tk.Frame(update_frame, bg='grey').pack(fill='x', pady=(0, 2))
                update_frame.pack(side='bottom', fill='x')

                update_label = tk.Label(update_frame,
                                        text=_('Too many requests. Try again later.'),
                                        bg=get_color('bottomframe'),
                                        fg=get_color('autologin_text_unavail'))
                update_label.pack(side='bottom')
        except q.Empty:
            master.after(300, get_output)

    t = threading.Thread(target=checkupdate)
    t.start()
    master.after(300, get_output)


def hide_update():
    global update_frame
    update_frame.pack_forget()


def show_update():
    global update_frame
    update_frame.pack(side='bottom', fill='x')


def update_frame_color():
    global update_label
    global update_code
    global update_frame
    global bundled
    update_frame.configure(bg=get_color('bottomframe'))
    update_label.configure(bg=get_color('bottomframe'))

    if not bundled:
        return
    elif update_code == 'avail':
        update_label.configure(fg=get_color('autologin_text_avail'))
    elif update_code == 'latest':
        update_label.configure(fg=get_color('text'))
    elif update_code == 'dev':
        update_label.configure(fg=get_color('text'))
    else:
        update_label.configure(fg=get_color('autologin_text_unavail'))
