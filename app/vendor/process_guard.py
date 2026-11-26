"""Fresh read-only Windows process inventory; enumeration errors fail closed."""
import ctypes,os
from ctypes import wintypes

class PROCESSENTRY32W(ctypes.Structure):
    _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),
              ('th32ProcessID',wintypes.DWORD),('th32DefaultHeapID',ctypes.c_size_t),
              ('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
              ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),
              ('dwFlags',wintypes.DWORD),('szExeFile',wintypes.WCHAR*260)]

def process_names(api=None):
    if api is None:
        if os.name!='nt':raise RuntimeError('Could not establish game closure on this platform')
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD];api.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
        api.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(PROCESSENTRY32W)];api.Process32FirstW.restype=wintypes.BOOL
        api.Process32NextW.argtypes=api.Process32FirstW.argtypes;api.Process32NextW.restype=wintypes.BOOL
        api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle.restype=wintypes.BOOL
    ctypes.set_last_error(0);snapshot=api.CreateToolhelp32Snapshot(2,0)
    if snapshot in (None,0,ctypes.c_void_p(-1).value):raise RuntimeError('Could not establish game closure: process snapshot failed ('+str(ctypes.get_last_error())+')')
    names=set();entry=PROCESSENTRY32W();entry.dwSize=ctypes.sizeof(entry)
    try:
        ctypes.set_last_error(0);found=api.Process32FirstW(snapshot,ctypes.byref(entry))
        while found:
            names.add(entry.szExeFile.casefold())
            ctypes.set_last_error(0);found=api.Process32NextW(snapshot,ctypes.byref(entry))
        error=ctypes.get_last_error()
        if error!=18:raise RuntimeError('Could not establish game closure: incomplete process inventory ('+str(error)+')')
        return names
    finally:
        if not api.CloseHandle(snapshot):raise RuntimeError('Could not close the process inventory safely')

def ensure_closed():
    if {name.casefold().removesuffix('.exe') for name in process_names()} & {'narakabladepoint','startgame'}:
        raise RuntimeError('Naraka or StartGame is running; close it before any file change')
