import sys
import os
import zipfile as zf
import locale

locale_buf = locale.getdefaultlocale()
LOCALE = locale_buf[0]


def pprint(content):
    print('    ' + content)


if not getattr(sys, 'frozen', False):
    print()
    pprint("Running on Python interpreter not supported")
    print()
    input('    Press Enter to exit...')
    sys.exit(0)


def invalidzip():
    print()
    if LOCALE == 'ko_KR':
        pprint('업데이트 압축 파일이 유효하지 않습니다.')
        pprint('프로그램을 재시작 하여 업데이트를 다시 시도하십시오.')
        print()
        pprint('----------------------------------------------------------')
        print()
        input('    Enter 키를 눌러서 나가기...')
    else:
        pprint('Update archive is invalid.')
        pprint('Restart the application and try again.')
        print()
        pprint('----------------------------------------------------------')
        print()
        input('    Press Enter to exit...')
    sys.exit(1)


cwd = os.getcwd()
pprint('Current working directory: ' + cwd)
print()
archive = os.path.join(cwd, 'update.zip')

if not os.path.isfile(archive) or not zf.is_zipfile(archive):
    invalidzip()
else:
    try:
        f = zf.ZipFile(archive, mode='r')
    except zf.BadZipFile:
        invalidzip()

if 'Steam Account Switcher.exe' not in f.namelist():
    invalidzip()

parent_dir = os.path.dirname(os.getcwd())

print()
if LOCALE == 'ko_KR':
    pprint('업데이트 설치 중...')
else:
    pprint('Installing update...')

try:
    f.extractall(members=(member for member in f.namelist() if 'updater' not in member))  # NOQA
except Exception:
    print()
    if LOCALE == 'ko_KR':
        pprint('업데이트 도중 오류가 발생하였습니다.')
        pprint('수동으로 update.zip을 연다음 압축해제 하십시오.')
        print()
        pprint('----------------------------------------------------------')
        print()
        input('    Enter 키를 눌러서 나가기...')
    else:
        pprint('Error occured during update process.')
        pprint('Manually update by extracting update.zip.')
        print()
        pprint('----------------------------------------------------------')
        print()
        input('    Press Enter to exit...')
    sys.exit(1)

f.close()

os.execv('Steam Account Switcher.exe', sys.argv)