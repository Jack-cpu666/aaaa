import sys
import time
import math
import socket
import threading
import numpy as np
import mss
import os
import ctypes
from ctypes import *
from ctypes.wintypes import *
# pynput is for the example engine, not directly used by Flask app
# from pynput.keyboard import Listener as KeyboardListener, Key, KeyCode
# from pynput.mouse import Listener as MouseListener, Button
from flask import Flask, request, render_template_string, jsonify, send_file
from waitress import serve
import json
import io
import zipfile
import random

# --- Configuration Store ---
# In a real app, this would be a database or user-session specific.
# For this example, it's a global variable holding the latest configuration.
current_config = {
    "theme": "light", # 'light' or 'dark'
    "detection_core": {
        "method": "color",
        "primary_target_color_hex": "#FFFF00",
        "color_tolerance_r": 15,
        "color_tolerance_g": 15,
        "color_tolerance_b": 15,
        "min_pixel_size": 5,
        "fov_shape": "circle",
        "fov_size_percent": 20,
        "scan_rate_fps": 60,
    },
    "aimbot_module": {
        "enabled": False,
        "always_on": False, # Corresponds to aimbot_always_on
        "activation_key": "mouse1",
        "targeting_priority": "closest_to_crosshair",
        "aim_location_offset_y": -5, # Corresponds to aim_offset
        "smoothing_factor": 0.5,
        "sensitivity_multiplier_left": 0.25, # Corresponds to left_sensitivity
        "sensitivity_multiplier_right": 0.25, # Corresponds to right_sensitivity
        "fov_pixels": 50, # Corresponds to aimbot_pixel_size
    },
    "triggerbot_module": {
        "enabled": False,
        "activation_key": "mouse2",
        "delay_ms": 100,
        "fire_interval_ms": 200, # Derived from gun_settings
        "fov_pixels": 4, # Corresponds to triggerbot_pixel_size
        "shoot_while_moving": False,
        "selected_gun": "Vandel", # Corresponds to selected_gun
    },
    "ui_overlay_designer": {
        "enabled": False,
        "config_json": json.dumps({"elements": [{"type": "text", "content": "Aimbot Active", "x": 10, "y": 10, "color": "#00FF00"}]}, indent=2),
    },
    "gun_settings": { # From original example
        "Vandel": 0.15,
        "OP": 4.5,
        "Sheriff": 0.55,
        "Shotgun": 0.05
    }
}

# --- Example Engine Code (RZCONTROL etc.) ---
# This is the code block provided by the user, intended for download.
# I've removed Flask/Waitress specific parts from it for standalone use.
EXAMPLE_ENGINE_PYTHON_CODE = r"""
import sys
import time
import math
import socket # Note: socket is used in the original for get_local_ip, not essential for core aimbot
import threading
import numpy as np
import mss
import os
import ctypes
from ctypes import *
from ctypes.wintypes import *
from pynput.keyboard import Listener as KeyboardListener, Key, KeyCode
from pynput.mouse import Listener as MouseListener, Button

# Ensure these are available or handled if this script is run standalone
try:
    ntdll = windll.ntdll
    kernel32 = windll.kernel32
except AttributeError:
    print("This script is intended for Windows environments with ntdll and kernel32.")
    print("If you are not on Windows, some features (RZCONTROL) will not work.")
    # Provide dummy objects if not on Windows to allow script to partially run/be inspected
    class DummyDLL:
        def __getattr__(self, name):
            def _dummy_func(*args, **kwargs):
                print(f"Warning: {name} called on a non-Windows system or DLL not found.")
                if name == "NtOpenDirectoryObject" or name == "NtQueryDirectoryObject":
                    return STATUS_UNSUCCESSFUL # Simulate failure
                if name == "CreateFileW":
                    return INVALID_HANDLE_VALUE
                return 0 # Default return
            return _dummy_func
    if 'win32' not in sys.platform:
        ntdll = DummyDLL()
        kernel32 = DummyDLL()


NTSTATUS = c_long
STATUS_SUCCESS = NTSTATUS(0x00000000).value
STATUS_UNSUCCESSFUL = NTSTATUS(0xC0000001).value
STATUS_BUFFER_TOO_SMALL = NTSTATUS(0xC0000023).value
PVOID = c_void_p
PWSTR = c_wchar_p
DIRECTORY_QUERY = 0x0001
OBJ_CASE_INSENSITIVE = 0x00000040
INVALID_HANDLE_VALUE = -1 if sys.platform == 'win32' else c_void_p(-1) # Match type
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3

class UNICODE_STRING(Structure):
    _fields_ = [("Length", USHORT),
                ("MaximumLength", USHORT),
                ("Buffer", PWSTR)]

class OBJECT_ATTRIBUTES(Structure):
    _fields_ = [
        ("Length", ULONG),
        ("RootDirectory", HANDLE),
        ("ObjectName", POINTER(UNICODE_STRING)),
        ("Attributes", ULONG),
        ("SecurityDescriptor", PVOID),
        ("SecurityQualityOfService", PVOID),
    ]

class OBJECT_DIRECTORY_INFORMATION(Structure):
    _fields_ = [
        ("Name", UNICODE_STRING),
        ("TypeName", UNICODE_STRING)
    ]

def InitializeObjectAttributes(InitializedAttributes, ObjectName, Attributes, RootDirectory, SecurityDescriptor):
    if sys.platform != 'win32': return
    memset(addressof(InitializedAttributes), 0, sizeof(InitializedAttributes))
    InitializedAttributes.Length = sizeof(InitializedAttributes)
    InitializedAttributes.ObjectName = ObjectName
    InitializedAttributes.Attributes = Attributes
    InitializedAttributes.RootDirectory = RootDirectory
    InitializedAttributes.SecurityDescriptor = SecurityDescriptor
    InitializedAttributes.SecurityQualityOfService = None

def RtlInitUnicodeString(DestinationString, Src):
    if sys.platform != 'win32': return STATUS_UNSUCCESSFUL
    memset(addressof(DestinationString), 0, sizeof(DestinationString))
    DestinationString.Buffer = cast(Src, PWSTR)
    # Ensure correct calculation for unicode buffer
    DestinationString.Length = (len(Src.value) * 2) if Src.value else 0 # len in characters * 2 bytes/char
    DestinationString.MaximumLength = DestinationString.Length + 2 # Add space for null terminator
    return STATUS_SUCCESS


def open_directory(root_handle, dir_path, desired_access):
    if sys.platform != 'win32': return None
    status = STATUS_UNSUCCESSFUL
    dir_handle = c_void_p()
    us_dir = UNICODE_STRING()
    p_us_dir = None
    if dir_path:
        w_dir = create_unicode_buffer(dir_path)
        status = RtlInitUnicodeString(us_dir, w_dir)
        p_us_dir = pointer(us_dir)
        if status != STATUS_SUCCESS:
            print(f"RtlInitUnicodeString failed for {dir_path}.")
            return None # Changed from sys.exit
    obj_attr = OBJECT_ATTRIBUTES()
    InitializeObjectAttributes(obj_attr, p_us_dir, OBJ_CASE_INSENSITIVE, root_handle, None)
    status = ntdll.NtOpenDirectoryObject(byref(dir_handle), desired_access, byref(obj_attr))
    if status != STATUS_SUCCESS:
        print(f"NtOpenDirectoryObject failed for {dir_path} with status {status}.")
        return None # Changed from sys.exit
    return dir_handle

def find_sym_link(dir_path, name):
    if sys.platform != 'win32': return False, None
    # Corrected path for NtOpenDirectoryObject to query \GLOBAL??
    dir_handle = open_directory(None, "\\GLOBAL??", DIRECTORY_QUERY)
    if not dir_handle:
        print("Failed to open directory \\GLOBAL??")
        return False, None # Changed from sys.exit

    status = STATUS_UNSUCCESSFUL
    query_context = ULONG(0)
    length = ULONG(0) # Initialize length
    # Allocate a buffer for OBJECT_DIRECTORY_INFORMATION. Start with a reasonable size.
    # This needs to be more robust in production, but for an example:
    buffer_size = 1024 
    obj_inf_buffer = create_string_buffer(buffer_size)
    found = False
    out = None

    while True:
        # First call to get the required buffer size
        status = ntdll.NtQueryDirectoryObject(dir_handle, None, 0, True, False, byref(query_context), byref(length))
        if status != STATUS_BUFFER_TOO_SMALL and status != STATUS_SUCCESS: # STATUS_SUCCESS can happen if context is already at end
            if query_context.value == 0 and status == STATUS_SUCCESS: # No more entries and first call was empty
                 break 
            print(f"NtQueryDirectoryObject (size query) failed with status {status:08X}. Length: {length.value}")
            if status == NTSTATUS(0x8000001A).value : # STATUS_NO_MORE_ENTRIES
                break
            # sys.exit(0) # Avoid exiting, just break or return
            break 
        
        if length.value == 0: # No data to read or end of directory
            break

        if length.value > buffer_size:
            obj_inf_buffer = create_string_buffer(length.value)
            buffer_size = length.value
        
        status = ntdll.NtQueryDirectoryObject(dir_handle, obj_inf_buffer, length, True, False, byref(query_context), byref(length))
        if status != STATUS_SUCCESS:
            if status == NTSTATUS(0x8000001A).value : # STATUS_NO_MORE_ENTRIES
                 break
            print(f"NtQueryDirectoryObject (data query) failed with status {status:08X}")
            # sys.exit(0) # Avoid exiting
            break
        
        # Process the buffer
        current_offset = 0
        while current_offset < length.value:
            # Assuming OBJECT_DIRECTORY_INFORMATION is the structure at the current offset
            # This part is complex because the buffer contains multiple entries and Name/TypeName buffers are inline
            # For simplicity, we'll just try to cast the start of the buffer.
            # A proper implementation would iterate through the linked list of entries if SingleEntry is False,
            # or process one entry if SingleEntry is True (as used here).
            
            # We are using SingleEntry=True, so obj_inf_buffer should point to one OBJECT_DIRECTORY_INFORMATION
            objinf = OBJECT_DIRECTORY_INFORMATION.from_buffer(obj_inf_buffer)

            # Check if Name.Buffer is valid and contains the string
            if objinf.Name.Buffer and objinf.Name.Length > 0:
                _name = wstring_at(objinf.Name.Buffer, objinf.Name.Length // 2) # Length is in bytes
                if name in _name:
                    found = True
                    out = _name
                    break # Found the item
            else: # No name, possibly end or malformed
                break
            
            # If SingleEntry is True, we process one entry and then NtQueryDirectoryObject should advance the context.
            # So we break the inner loop to make the next call to NtQueryDirectoryObject.
            break 
        
        if found:
            break
        
        if query_context.value == 0 and not found: # Reached end and not found
            break


    kernel32.CloseHandle(dir_handle)
    return found, out


try:
    c_int32 = c_int # Already defined usually
except NameError:
    c_int32 = c_int

BOOL = c_int # wintypes.BOOL is c_long, but often c_int is used in C examples for BOOL

def enum(**enums):
    return type("Enum", (), enums)

MOUSE_CLICK = enum(
    LEFT_DOWN=1,
    LEFT_UP=2,
    RIGHT_DOWN=4,
    RIGHT_UP=8,
    SCROLL_CLICK_DOWN=16,
    SCROLL_CLICK_UP=32,
    BACK_DOWN=64,
    BACK_UP=128,
    FOWARD_DOWN=256,
    FOWARD_UP=512,
    SCROLL_DOWN=4287104000, # This seems specific, usually mouse wheel uses MOUSEEVENTF_WHEEL
    SCROLL_UP=7865344,     # and a mouseData value. The RZCONTROL driver might be different.
)

KEYBOARD_INPUT_TYPE = enum(KEYBOARD_DOWN=0, KEYBOARD_UP=1) # Values seem specific to RZCONTROL

class RZCONTROL_IOCTL_STRUCT(Structure):
    _fields_ = [
        ("unk0", c_int32),
        ("unk1", c_int32),
        ("max_val_or_scan_code", c_int32), # For keyboard, this is (scan_code << 16)
        ("click_mask_or_key_state", c_int32), # For keyboard, this is up_down (0 or 1)
        ("unk3", c_int32),
        ("x", c_int32),
        ("y", c_int32),
        ("unk4", c_int32),
    ]

IOCTL_MOUSE_OR_KEYBOARD = 0x88883020 # The example uses the same IOCTL for mouse and keyboard
MAX_VAL = 65536 # For absolute mouse positioning
RZCONTROL_TYPE_MOUSE = 2
RZCONTROL_TYPE_KEYBOARD = 1

class RZCONTROL:
    hDevice = INVALID_HANDLE_VALUE if sys.platform == 'win32' else c_void_p(-1)

    def __init__(self):
        pass

    def init(self):
        if sys.platform != 'win32':
            print("RZCONTROL is Windows-specific. Skipping init on non-Windows.")
            return False
            
        if RZCONTROL.hDevice != INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(RZCONTROL.hDevice)
            RZCONTROL.hDevice = INVALID_HANDLE_VALUE

        # The find_sym_link logic needs to be robust.
        # For now, assuming it works or we hardcode if necessary for testing.
        # The original find_sym_link needs careful review for correctness on buffer handling.
        # Let's try with the name directly, this is often how drivers are found.
        # common_paths = [
        #     r"\\.\RZCONTROL", 
        #     r"\\?\Global\RZCONTROL",
        # ]
        # found_path = None
        # for path_attempt in common_paths:
        #     handle = kernel32.CreateFileW(
        #         create_unicode_buffer(path_attempt),
        #         0xC0000000, # GENERIC_READ | GENERIC_WRITE - more standard
        #         FILE_SHARE_READ | FILE_SHARE_WRITE,
        #         None, # Security attributes
        #         OPEN_EXISTING,
        #         0,    # Flags and attributes
        #         None  # Template file
        #     )
        #     if handle != INVALID_HANDLE_VALUE:
        #         found_path = path_attempt
        #         RZCONTROL.hDevice = handle
        #         break
        
        # Using find_sym_link as per original code, with corrections
        found, name = find_sym_link("\\GLOBAL??", "RZCONTROL") # Corrected dir for NtOpenDirectoryObject
        if not found or not name:
            print("RZCONTROL symbolic link not found.")
            # Try common direct paths as a fallback
            path_attempt = r"\\.\RZCONTROL" 
            handle = kernel32.CreateFileW(
                create_unicode_buffer(path_attempt),
                0xC0000000, # GENERIC_READ | GENERIC_WRITE
                FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None
            )
            if handle == INVALID_HANDLE_VALUE:
                print(f"Failed to open RZCONTROL device directly at {path_attempt}. Error: {kernel32.GetLastError()}")
                return False
            RZCONTROL.hDevice = handle
            print(f"Opened RZCONTROL directly at {path_attempt}")

        else:
            sym_link = "\\\\?\\" + name # Construct full path for CreateFileW
            RZCONTROL.hDevice = kernel32.CreateFileW(
                create_unicode_buffer(sym_link),
                0xC0000000, # GENERIC_READ | GENERIC_WRITE (or 0 for no specific access if driver allows)
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, # Security attributes
                OPEN_EXISTING,
                0,    # Flags and attributes
                None  # Template file
            )

        if RZCONTROL.hDevice == INVALID_HANDLE_VALUE:
            print(f"Failed to open RZCONTROL device. Error: {kernel32.GetLastError()}")
            return False
        
        print("RZCONTROL initialized successfully.")
        return True

    def close(self):
        if sys.platform == 'win32' and RZCONTROL.hDevice != INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(RZCONTROL.hDevice)
            RZCONTROL.hDevice = INVALID_HANDLE_VALUE
            print("RZCONTROL handle closed.")

    def _impl_ioctl(self, control_type, param2, param3_click_mask_or_key_state, x, y, param_max_val_or_scan_code):
        if sys.platform != 'win32' or RZCONTROL.hDevice == INVALID_HANDLE_VALUE:
            # print("RZCONTROL not initialized or not on Windows.")
            return False # Silently fail if not init for cleaner operation

        ioctl_struct = RZCONTROL_IOCTL_STRUCT(
            unk0=0,  # Often 0 or a sequence number
            unk1=control_type, # RZCONTROL_TYPE_MOUSE or RZCONTROL_TYPE_KEYBOARD
            max_val_or_scan_code=param_max_val_or_scan_code, # MAX_VAL for abs mouse / (scan_code << 16) for kbd
            click_mask_or_key_state=param3_click_mask_or_key_state, # click_mask for mouse / key_state for kbd
            unk3=0, # Often related to status or sub-command
            x=x,
            y=y,
            unk4=0  # Often 0
        )
        
        bytes_returned = c_ulong()
        
        success = kernel32.DeviceIoControl(
            RZCONTROL.hDevice,
            IOCTL_MOUSE_OR_KEYBOARD,
            byref(ioctl_struct),
            sizeof(ioctl_struct),
            None, # Output buffer
            0,    # Output buffer size
            byref(bytes_returned),
            None  # Overlapped
        )
        
        if not success:
            print(f"DeviceIoControl failed with error: {kernel32.GetLastError()}")
            # Optionally re-initialize or handle error
            # self.init() # Be careful with re-init loops
            return False
        return True

    def mouse_move(self, dx, dy, relative=True):
        # RZCONTROL seems to use absolute coordinates based on max_val
        # If relative is true, we need current position, which this driver doesn't provide.
        # So, we assume dx, dy are relative movements to be ADDED to current position,
        # but RZCONTROL itself takes absolute. This requires a more complex implementation
        # or the driver has a relative mode not shown.
        # The original code's `from_start_point` suggests it can be relative (dx, dy) or absolute (x,y).
        # If `from_start_point` (relative) is True, max_val is 0.
        # If `from_start_point` (relative) is False, max_val is MAX_VAL (absolute coords).

        # Let's match the original logic:
        # from_start_point=True means dx, dy are relative movements.
        # from_start_point=False means dx, dy are absolute screen coords.
        
        current_x, current_y = 0, 0 # Placeholder if we need to simulate relative from absolute

        if relative: # dx, dy are the relative changes
            # The RZCONTROL struct seems to always take absolute values for x,y if max_val_or_scan_code is 0.
            # If max_val_or_scan_code is MAX_VAL, then x,y are absolute within that range.
            # This is confusing. Let's assume `mouse_move(dx, dy, True)` means send these as direct values.
            # The `max_val` field in the struct is then 0 as per original.
            return self._impl_ioctl(RZCONTROL_TYPE_MOUSE, 0, 0, dx, dy, 0) # param2=0, click_mask=0, max_val=0 for relative
        else: # dx, dy are absolute coordinates
            # Clip to MAX_VAL range
            x_abs = max(0, min(dx, MAX_VAL))
            y_abs = max(0, min(dy, MAX_VAL))
            return self._impl_ioctl(RZCONTROL_TYPE_MOUSE, 0, 0, x_abs, y_abs, MAX_VAL) # max_val = MAX_VAL for absolute

    def mouse_click(self, click_mask):
        # For clicks, x and y are often 0, max_val_or_scan_code is 0
        return self._impl_ioctl(RZCONTROL_TYPE_MOUSE, 0, click_mask, 0, 0, 0)

    def keyboard_input(self, scan_code, key_state_up_down): # key_state: 0 for KEYBOARD_DOWN, 1 for KEYBOARD_UP
        # scan_code is the hardware scan code.
        # key_state_up_down is 0 for press, 1 for release.
        # The original code puts (scan_code << 16) into max_val_or_scan_code.
        # And up_down into click_mask_or_key_state.
        param_scan_code_shifted = int(scan_code) << 16
        return self._impl_ioctl(RZCONTROL_TYPE_KEYBOARD, 0, key_state_up_down, 0, 0, param_scan_code_shifted)


# --- Global RZCONTROL instance for the example engine ---
rz_controller = RZCONTROL() # Instantiate, but init() must be called by user

# --- Aimbot/Triggerbot Logic (from user prompt, slightly adapted) ---
# This part would be part of the "engine" that the user downloads and runs locally.
# It uses the RZCONTROL class.

movement_keys_pressed = set()
mouse_buttons_state = {"left": False, "right": False}

# Standard scan codes (Set 1, Make codes) - for KEYBOARD_INPUT_TYPE
# These might need adjustment based on game or specific keyboard layouts.
# Example: 'W' key
SCANCODE_W_MAKE = 0x11
SCANCODE_A_MAKE = 0x1E
SCANCODE_S_MAKE = 0x1F
SCANCODE_D_MAKE = 0x20
SCANCODE_UP_MAKE = 0x48 # Arrow Up
SCANCODE_DOWN_MAKE = 0x50 # Arrow Down
SCANCODE_LEFT_MAKE = 0x4B # Arrow Left
SCANCODE_RIGHT_MAKE = 0x4D # Arrow Right

# Mapping pynput Keys to scancodes (example, would need to be comprehensive)
PYNPUT_TO_SCANCODE = {
    KeyCode.from_char('w'): SCANCODE_W_MAKE, KeyCode.from_char('W'): SCANCODE_W_MAKE,
    KeyCode.from_char('a'): SCANCODE_A_MAKE, KeyCode.from_char('A'): SCANCODE_A_MAKE,
    KeyCode.from_char('s'): SCANCODE_S_MAKE, KeyCode.from_char('S'): SCANCODE_S_MAKE,
    KeyCode.from_char('d'): SCANCODE_D_MAKE, KeyCode.from_char('D'): SCANCODE_D_MAKE,
    Key.up: SCANCODE_UP_MAKE,
    Key.down: SCANCODE_DOWN_MAKE,
    Key.left: SCANCODE_LEFT_MAKE,
    Key.right: SCANCODE_RIGHT_MAKE,
}

# These are pynput keys
MOVEMENT_KEYS_PYNPUT = {
    Key.up, Key.down, Key.left, Key.right,
    KeyCode.from_char('w'), KeyCode.from_char('W'),
    KeyCode.from_char('a'), KeyCode.from_char('A'),
    KeyCode.from_char('s'), KeyCode.from_char('S'),
    KeyCode.from_char('d'), KeyCode.from_char('D')
}

def is_enemy_color_example(img_bgr, config):
    # Example: use yellow from the original logic. Config could specify RGB thresholds.
    # For this example, let's use the hardcoded values from the original prompt.
    # img_bgr is a NumPy array (H, W, C) where C is BGR.
    b = img_bgr[:, :, 0].astype(np.int32)
    g = img_bgr[:, :, 1].astype(np.int32)
    r = img_bgr[:, :, 2].astype(np.int32)
    
    # These thresholds would come from `config.detection_core` in a real scenario
    # For example: config.detection_core.color_r_min, .color_g_min, etc.
    # Using original prompt's "yellow"
    min_r, min_g, max_b = 218, 100, 85
    max_diff_rg, min_diff_rb, min_diff_gb = 15, 20, 20

    mask = (r >= min_r) & (g >= min_g) & (b <= max_b) & \
           (np.abs(r - g) <= max_diff_rg) & \
           ((r - b) >= min_diff_rb) & \
           ((g - b) >= min_diff_gb)
    return mask

def dynamic_sensitivity_adjust(dx, dy, base_sensitivity, threshold=5, reduction_factor=0.5):
    distance = math.sqrt(dx*dx + dy*dy)
    if distance < threshold:
        return base_sensitivity * reduction_factor
    return base_sensitivity

def aim_at_target_rz(dx, dy, left_pressed, right_pressed, left_sens, right_sens, sens_multiplier, aim_offset_y, config):
    global rz_controller
    if not rz_controller.hDevice or rz_controller.hDevice == INVALID_HANDLE_VALUE:
        # print("Aim: RZCONTROL not ready.")
        return

    base_sensitivity = left_sens if left_pressed else (right_sens if right_pressed else left_sens)
    
    # Use dynamic sensitivity from config if enabled
    use_dynamic_sens = config.get("aimbot_module", {}).get("dynamic_sensitivity_enabled", True) # Default to True
    dynamic_sens_threshold = config.get("aimbot_module", {}).get("dynamic_sensitivity_threshold", 5)
    dynamic_sens_reduction = config.get("aimbot_module", {}).get("dynamic_sensitivity_reduction", 0.5)

    if use_dynamic_sens:
        base_sensitivity = dynamic_sensitivity_adjust(dx, dy, base_sensitivity, dynamic_sens_threshold, dynamic_sens_reduction)

    # Original scaling: dx * 0.6 * base_sensitivity * sensitivity_multiplier
    # The sens_multiplier is part of the base_sensitivity in the new config structure
    # Let's simplify: dx_scaled = dx * base_sensitivity
    # The 0.6 factor can be part of the sensitivity tuning or a separate "smoothness_factor"
    
    smooth_factor = config.get("aimbot_module", {}).get("smoothing_factor", 0.6) # Using 0.6 as default

    move_x = int(dx * smooth_factor * base_sensitivity) # base_sensitivity already includes user multiplier
    move_y = int(dy * smooth_factor * base_sensitivity + aim_offset_y)
    
    # rz_controller.mouse_move expects relative movements if its `relative` flag is True
    rz_controller.mouse_move(move_x, move_y, relative=True)


class AimbotTriggerbotEngineThread(threading.Thread):
    def __init__(self, profile_config):
        super().__init__()
        self.daemon = True
        self.running = False
        self.profile_config = profile_config # Loaded from .pfprofile
        self.last_shot_time = 0
        self.sct = None

        # FPS calculation
        self.current_fps = 0.0
        self._frame_count = 0
        self._fps_start_time = time.time()
        
        # For listening to local mouse/keyboard (not for sending, RZCONTROL does that)
        self.kb_listener_instance = None
        self.mouse_listener_instance = None

    def _on_key_press(self, key):
        if key in MOVEMENT_KEYS_PYNPUT:
            movement_keys_pressed.add(key)

    def _on_key_release(self, key):
        if key in MOVEMENT_KEYS_PYNPUT:
            movement_keys_pressed.discard(key)
        if key == Key.f1: # Example: Toggle running state
            self.running = not self.running
            print(f"Engine running state: {self.running}")
        if key == Key.f2: # Example: Reload config (conceptual)
            print("Config reload requested (conceptual).")


    def _on_mouse_click(self, x, y, button, pressed):
        if button == Button.left:
            mouse_buttons_state["left"] = pressed
        elif button == Button.right:
            mouse_buttons_state["right"] = pressed

    def update_config(self, new_profile_config):
        self.profile_config = new_profile_config
        print("Engine configuration updated.")

    def run(self):
        global rz_controller
        if not rz_controller.init():
            print("Failed to initialize RZCONTROL. Engine thread stopping.")
            return
        
        self.kb_listener_instance = KeyboardListener(on_press=self._on_key_press, on_release=self._on_key_release)
        self.mouse_listener_instance = MouseListener(on_click=self._on_mouse_click)
        
        self.kb_listener_instance.start()
        self.mouse_listener_instance.start()
        print("Engine thread started. Press F1 to toggle scanning. Ensure RZCONTROL is working.")

        with mss.mss() as self.sct:
            monitor_info = self.sct.monitors[1] # Main monitor
            screen_width = monitor_info['width']
            screen_height = monitor_info['height']
            mid_x = screen_width // 2
            mid_y = screen_height // 2

            while True:
                if not self.running:
                    time.sleep(0.1)
                    self.current_fps = 0 # Reset FPS when not running
                    continue

                cfg_aim = self.profile_config.get("aimbot_module", {})
                cfg_trig = self.profile_config.get("triggerbot_module", {})
                cfg_detect = self.profile_config.get("detection_core", {})
                gun_settings = self.profile_config.get("gun_settings", {})

                aimbot_enabled = cfg_aim.get("enabled", False)
                triggerbot_enabled = cfg_trig.get("enabled", False)

                if not aimbot_enabled and not triggerbot_enabled:
                    time.sleep(0.05)
                    continue

                # FOV for detection (shared by aimbot/triggerbot for target finding)
                # In the original code, aimbot_pixel_size was the main FOV.
                # Let's use the detection_core.fov_size_percent for screen capture area.
                # Then aimbot_module.fov_pixels and triggerbot_module.fov_pixels for their specific logic within that capture.

                fov_percent = cfg_detect.get("fov_size_percent", 20) / 100.0
                scan_area_size = min(int(screen_width * fov_percent), int(screen_height * fov_percent))
                scan_area_size = max(10, scan_area_size) # Ensure minimum size

                monitor = {
                    "top": mid_y - scan_area_size // 2,
                    "left": mid_x - scan_area_size // 2,
                    "width": scan_area_size,
                    "height": scan_area_size
                }
                # Ensure monitor dimensions are valid
                monitor["top"] = max(0, monitor["top"])
                monitor["left"] = max(0, monitor["left"])
                monitor["width"] = min(monitor["width"], screen_width - monitor["left"])
                monitor["height"] = min(monitor["height"], screen_height - monitor["top"])

                if monitor["width"] <=0 or monitor["height"] <=0:
                    # print("Invalid scan monitor dimensions, skipping frame.")
                    time.sleep(0.1)
                    continue
                
                try:
                    screenshot_bgr = np.array(self.sct.grab(monitor))[:,:,:3] # BGR format
                except mss.exception.ScreenShotError as e:
                    # print(f"ScreenShotError: {e}. Retrying.")
                    time.sleep(0.1) # Wait a bit if screenshot fails
                    continue


                enemy_mask = is_enemy_color_example(screenshot_bgr, self.profile_config)
                enemy_detected_in_scan_area = enemy_mask.any()
                
                target_coords_scan_area = None
                if enemy_detected_in_scan_area:
                    indices = np.where(enemy_mask)
                    if indices[0].size > 0 and indices[1].size > 0:
                        # Target center relative to top-left of screenshot
                        target_x_ss = np.mean(indices[1]) 
                        target_y_ss = np.mean(indices[0])
                        target_coords_scan_area = (target_x_ss, target_y_ss)


                # Aimbot Logic
                if aimbot_enabled and enemy_detected_in_scan_area and target_coords_scan_area:
                    aim_always_on = cfg_aim.get("always_on", False)
                    # Activation key logic (e.g. mouse_buttons_state["left"])
                    # For simplicity, using always_on or if a mouse button (monitored by pynput) is pressed.
                    # A more robust solution would check specific keybind from config.
                    aim_active_condition = aim_always_on or mouse_buttons_state["left"] or mouse_buttons_state["right"]

                    if aim_active_condition:
                        # Convert target coords from screenshot space to screen center relative
                        # This is the dx, dy needed for mouse_move
                        dx_from_center = target_coords_scan_area[0] - scan_area_size // 2
                        dy_from_center = target_coords_scan_area[1] - scan_area_size // 2
                        
                        # Check if target is within aimbot's specific FOV (if smaller than scan FOV)
                        aim_fov_pixels = cfg_aim.get("fov_pixels", scan_area_size) # Use scan_area_size if not set
                        if math.sqrt(dx_from_center**2 + dy_from_center**2) <= aim_fov_pixels / 2:
                            aim_at_target_rz(
                                dx=dx_from_center,
                                dy=dy_from_center,
                                left_pressed=mouse_buttons_state["left"],
                                right_pressed=mouse_buttons_state["right"],
                                left_sens=cfg_aim.get("sensitivity_multiplier_left", 0.25),
                                right_sens=cfg_aim.get("sensitivity_multiplier_right", 0.25),
                                sens_multiplier=1.0, # Already incorporated in left/right_sens
                                aim_offset_y=cfg_aim.get("aim_location_offset_y", -5),
                                config=self.profile_config
                            )

                # Triggerbot Logic
                if triggerbot_enabled and enemy_detected_in_scan_area and target_coords_scan_area:
                    tb_fov_pixels = cfg_trig.get("fov_pixels", 4)
                    
                    # Check if target is within triggerbot's FOV (center of the scan area)
                    # Target coords are relative to scan area top-left. Center of scan area is (scan_area_size/2, scan_area_size/2)
                    dist_to_center_x = abs(target_coords_scan_area[0] - scan_area_size // 2)
                    dist_to_center_y = abs(target_coords_scan_area[1] - scan_area_size // 2)

                    if dist_to_center_x <= tb_fov_pixels / 2 and dist_to_center_y <= tb_fov_pixels / 2:
                        # Target is in triggerbot's crosshair FOV
                        current_time = time.time()
                        shoot_while_moving_allowed = cfg_trig.get("shoot_while_moving", False)
                        
                        is_moving = len(movement_keys_pressed) > 0
                        
                        if shoot_while_moving_allowed or not is_moving:
                            # if not mouse_buttons_state["left"]: # Don't shoot if already holding left click
                                selected_gun = cfg_trig.get("selected_gun", "Vandel")
                                gun_interval = gun_settings.get(selected_gun, 0.25) # Default interval

                                if current_time - self.last_shot_time >= gun_interval:
                                    rz_controller.mouse_click(MOUSE_CLICK.LEFT_DOWN)
                                    # Small delay for UP, or driver handles it. Original had separate calls.
                                    time.sleep(0.02) # Short delay between down and up
                                    rz_controller.mouse_click(MOUSE_CLICK.LEFT_UP)
                                    self.last_shot_time = current_time
                
                # FPS calculation
                self._frame_count += 1
                elapsed = time.time() - self._fps_start_time
                if elapsed >= 1.0:
                    self.current_fps = self._frame_count / elapsed
                    self._frame_count = 0
                    self._fps_start_time = time.time()
                    # print(f"Engine FPS: {self.current_fps:.2f}")


                # Control scan rate
                scan_rate_target = cfg_detect.get("scan_rate_fps", 60)
                if scan_rate_target > 0:
                    sleep_duration = 1.0 / scan_rate_target - (time.time() - self._fps_start_time) # Approximate
                    if sleep_duration > 0:
                         time.sleep(sleep_duration)
                else:
                    time.sleep(0.001) # Minimal sleep if no target rate or very high

        if self.kb_listener_instance: self.kb_listener_instance.stop()
        if self.mouse_listener_instance: self.mouse_listener_instance.stop()
        rz_controller.close()
        print("Engine thread stopped and resources released.")

# --- Flask App ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- HTML TEMPLATES ---

# Landing Page HTML
LANDING_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PrecisionForge - Craft Your Tactical Edge</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color-light: #f0f4f8; /* Light Slate */
            --text-color-light: #333;
            --primary-color-light: #3498db; /* Light Blue */
            --secondary-color-light: #2ecc71; /* Light Green */
            --card-bg-light: #ffffff;
            --border-color-light: #d1d8e0;

            --bg-color-dark: #2c3e50; /* Dark Slate */
            --text-color-dark: #ecf0f1;
            --primary-color-dark: #5dade2; /* Brighter Blue for Dark */
            --secondary-color-dark: #27ae60; /* Brighter Green for Dark */
            --card-bg-dark: #34495e;
            --border-color-dark: #4a627a;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
            transition: background-color 0.3s, color 0.3s;
            line-height: 1.6;
        }
        .light-theme {
            background-color: var(--bg-color-light);
            color: var(--text-color-light);
        }
        .dark-theme {
            background-color: var(--bg-color-dark);
            color: var(--text-color-dark);
        }
        .container {
            width: 90%;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        /* Header & Nav */
        header {
            padding: 10px 0;
            border-bottom: 1px solid var(--border-color-light);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .dark-theme header { border-bottom-color: var(--border-color-dark); }
        header .logo { font-size: 1.8em; font-weight: bold; color: var(--primary-color-light); }
        .dark-theme header .logo { color: var(--primary-color-dark); }
        nav a { margin-left: 20px; text-decoration: none; font-weight: 500; }
        nav a:hover { text-decoration: underline; }
        .light-theme nav a { color: var(--text-color-light); }
        .dark-theme nav a { color: var(--text-color-dark); }
        
        .theme-toggle {
            cursor: pointer;
            font-size: 1.5em;
            background: none;
            border: none;
            padding: 5px;
        }
        .light-theme .theme-toggle { color: var(--text-color-light); }
        .dark-theme .theme-toggle { color: var(--text-color-dark); }

        /* Hero Section */
        .hero {
            text-align: center;
            padding: 80px 20px;
            background: linear-gradient(135deg, var(--primary-color-light), var(--secondary-color-light));
            color: white;
            position: relative;
            overflow: hidden;
        }
        .dark-theme .hero {
            background: linear-gradient(135deg, var(--primary-color-dark), var(--secondary-color-dark));
        }
        .hero h1 { font-size: 3em; margin-bottom: 10px; font-weight: 700; }
        .hero p { font-size: 1.3em; margin-bottom: 30px; opacity: 0.9; }
        .cta-button {
            background-color: white;
            color: var(--primary-color-light);
            padding: 15px 30px;
            text-decoration: none;
            font-size: 1.1em;
            font-weight: bold;
            border-radius: 50px;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            display: inline-block;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        .dark-theme .cta-button { color: var(--primary-color-dark); }
        .cta-button:hover {
            transform: translateY(-3px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
        }
        /* Animated Background for Hero */
        .hero-bg-animation {
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            z-index: -1; /* Behind content */
            opacity: 0.1;
        }
        .hero-bg-animation span {
            position: absolute;
            display: block;
            width: 20px; height: 20px;
            background: rgba(255,255,255,0.5);
            animation: animate-bg 25s linear infinite;
            bottom: -150px; /* Start off screen */
            border-radius: 50%;
        }
        /* Different sizes and delays for particles */
        .hero-bg-animation span:nth-child(1){ left: 25%; width: 80px; height: 80px; animation-delay: 0s; }
        .hero-bg-animation span:nth-child(2){ left: 10%; width: 20px; height: 20px; animation-delay: 2s; animation-duration: 12s; }
        .hero-bg-animation span:nth-child(3){ left: 70%; width: 20px; height: 20px; animation-delay: 4s; }
        .hero-bg-animation span:nth-child(4){ left: 40%; width: 60px; height: 60px; animation-delay: 0s; animation-duration: 18s; }
        .hero-bg-animation span:nth-child(5){ left: 65%; width: 20px; height: 20px; animation-delay: 0s; }
        .hero-bg-animation span:nth-child(6){ left: 75%; width: 110px; height: 110px; animation-delay: 3s; }
        .hero-bg-animation span:nth-child(7){ left: 35%; width: 150px; height: 150px; animation-delay: 7s; }
        .hero-bg-animation span:nth-child(8){ left: 50%; width: 25px; height: 25px; animation-delay: 15s; animation-duration: 45s; }
        .hero-bg-animation span:nth-child(9){ left: 20%; width: 15px; height: 15px; animation-delay: 2s; animation-duration: 35s; }
        .hero-bg-animation span:nth-child(10){ left: 85%; width: 150px; height: 150px; animation-delay: 0s; animation-duration: 11s; }

        @keyframes animate-bg {
            0% { transform: translateY(0) rotate(0deg); opacity: 1; }
            100% { transform: translateY(-1000px) rotate(720deg); opacity: 0; }
        }

        /* Sections */
        .section { padding: 60px 0; }
        .section-title { text-align: center; font-size: 2.5em; margin-bottom: 40px; position: relative; }
        .section-title::after {
            content: ''; display: block; width: 80px; height: 4px;
            background: var(--primary-color-light);
            margin: 10px auto 0;
            border-radius: 2px;
        }
        .dark-theme .section-title::after { background: var(--primary-color-dark); }

        /* Features Grid */
        .features-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 30px;
        }
        .feature-card {
            background-color: var(--card-bg-light);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.08);
            text-align: center;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .dark-theme .feature-card { background-color: var(--card-bg-dark); box-shadow: 0 5px 20px rgba(0,0,0,0.2); }
        .feature-card:hover { transform: translateY(-5px); box-shadow: 0 8px 25px rgba(0,0,0,0.12); }
        .dark-theme .feature-card:hover { box-shadow: 0 8px 25px rgba(0,0,0,0.3); }
        .feature-card .icon { font-size: 3em; margin-bottom: 20px; color: var(--primary-color-light); }
        .dark-theme .feature-card .icon { color: var(--primary-color-dark); }
        .feature-card h3 { font-size: 1.5em; margin-bottom: 10px; }
        .feature-card p { font-size: 0.95em; opacity: 0.8; }

        /* How It Works */
        .how-it-works-steps {
            display: flex;
            justify-content: space-around;
            flex-wrap: wrap;
            gap: 20px;
        }
        .step-card {
            background-color: var(--card-bg-light);
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.07);
            width: 22%;
            min-width: 200px;
            text-align: center;
        }
        .dark-theme .step-card { background-color: var(--card-bg-dark); box-shadow: 0 5px 15px rgba(0,0,0,0.15); }
        .step-card .step-number {
            font-size: 2em; font-weight: bold;
            color: var(--primary-color-light);
            display: inline-block;
            width: 50px; height: 50px; line-height: 50px;
            border: 2px solid var(--primary-color-light);
            border-radius: 50%;
            margin-bottom: 15px;
        }
        .dark-theme .step-card .step-number { color: var(--primary-color-dark); border-color: var(--primary-color-dark); }
        .step-card h4 { font-size: 1.2em; margin-bottom: 8px; }

        /* Testimonials */
        .testimonials-slider { display: flex; gap: 30px; overflow-x: auto; padding-bottom: 20px; }
        .testimonial-card {
            background-color: var(--card-bg-light);
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.07);
            min-width: 300px;
            flex-shrink: 0;
        }
        .dark-theme .testimonial-card { background-color: var(--card-bg-dark); box-shadow: 0 5px 15px rgba(0,0,0,0.15); }
        .testimonial-card p { font-style: italic; margin-bottom: 15px; }
        .testimonial-card .author { font-weight: bold; text-align: right; color: var(--secondary-color-light); }
        .dark-theme .testimonial-card .author { color: var(--secondary-color-dark); }

        /* Footer */
        footer {
            background-color: #2c3e50; /* Dark footer for both themes for contrast */
            color: #ecf0f1;
            text-align: center;
            padding: 40px 20px;
            margin-top: 50px;
        }
        .footer-cta h2 { font-size: 2em; margin-bottom: 20px; }
        .footer-cta .cta-button { background-color: var(--primary-color-dark); color: white; }
        .ethical-reminder {
            margin-top: 30px;
            font-size: 0.85em;
            opacity: 0.7;
            max-width: 800px;
            margin-left: auto;
            margin-right: auto;
        }
        .copyright { margin-top: 20px; font-size: 0.9em; opacity: 0.6; }

        @media (max-width: 768px) {
            .hero h1 { font-size: 2.2em; }
            .hero p { font-size: 1.1em; }
            .section-title { font-size: 2em; }
            .how-it-works-steps .step-card { width: 45%; margin-bottom: 20px; }
            header { flex-direction: column; gap: 10px; }
            nav { margin-top: 10px; }
        }
    </style>
</head>
<body class="light-theme">
    <header class="container">
        <div class="logo">PrecisionForge</div>
        <nav>
            <a href="#features">Features</a>
            <a href="#how-it-works">How It Works</a>
            <a href="#testimonials">Testimonials</a>
            <a href="/forge">Forge UI</a>
            <button id="themeToggle" class="theme-toggle" title="Toggle Theme"><i class="fas fa-moon"></i></button>
        </nav>
    </header>

    <section class="hero">
        <div class="hero-bg-animation">
            <span></span><span></span><span></span><span></span><span></span>
            <span></span><span></span><span></span><span></span><span></span>
        </div>
        <div class="container">
            <h1>PrecisionForge: Craft Your Personalized Tactical Edge.</h1>
            <p>Unleash unparalleled customization. Design, simulate, and refine your unique aiming and response assistants with an intuitive, powerful web-based suite.</p>
            <a href="/forge" class="cta-button">Start Forging Now</a>
        </div>
    </section>

    <section id="features" class="section">
        <div class="container">
            <h2 class="section-title">Core Features</h2>
            <div class="features-grid">
                <div class="feature-card">
                    <div class="icon"><i class="fas fa-cogs"></i></div>
                    <h3>Modular Design</h3>
                    <p>Pick and choose components: Aimbot, Triggerbot, UI Overlays, Utility Scripts. Build what you need.</p>
                </div>
                <div class="feature-card">
                    <div class="icon"><i class="fas fa-sliders-h"></i></div>
                    <h3>Deep Customization</h3>
                    <p>Tweak every parameter, from detection algorithms and sensitivity curves to visual feedback.</p>
                </div>
                <div class="feature-card">
                    <div class="icon"><i class="fas fa-vr-cardboard"></i></div>
                    <h3>Live Simulation</h3>
                    <p>Test your creations in real-time against dynamic dummy targets and scenarios in our built-in simulator.</p>
                </div>
                <div class="feature-card">
                    <div class="icon"><i class="fas fa-drafting-compass"></i></div>
                    <h3>Visual Scripting (Conceptual)</h3>
                    <p>Drag-and-drop logic blocks or dive into an advanced code editor. For all skill levels.</p>
                </div>
                <div class="feature-card">
                    <div class="icon"><i class="fas fa-user-cog"></i></div>
                    <h3>Profile Management</h3>
                    <p>Save, load, and (soon) share your unique configurations with the community.</p>
                </div>
                <div class="feature-card">
                    <div class="icon"><i class="fas fa-cloud-download-alt"></i></div>
                    <h3>Cross-Platform Engine</h3>
                    <p>Download a lightweight core engine (example provided) and your personalized configuration profile.</p>
                </div>
            </div>
        </div>
    </section>

    <section id="how-it-works" class="section" style="background-color: var(--card-bg-light);">
        <div class="container dark-theme" style="background-color: var(--card-bg-light); color: var(--text-color-light);"> <!-- Force light for this section content -->
             <h2 class="section-title" style="color: var(--text-color-light);">How It Works</h2>
             <div class="how-it-works-steps">
                <div class="step-card" style="background-color: #fff; color: #333;"> <!-- Force light for card -->
                    <div class="step-number" style="color: var(--primary-color-light); border-color: var(--primary-color-light);">1</div>
                    <h4>Design Modules</h4>
                    <p>Use our intuitive Forge UI to select and configure Aimbot, Triggerbot, and other elements.</p>
                </div>
                <div class="step-card" style="background-color: #fff; color: #333;">
                     <div class="step-number" style="color: var(--primary-color-light); border-color: var(--primary-color-light);">2</div>
                    <h4>Simulate & Iterate</h4>
                    <p>Test rigorously in our advanced simulation chamber. Analyze performance with detailed graphs.</p>
                </div>
                <div class="step-card" style="background-color: #fff; color: #333;">
                     <div class="step-number" style="color: var(--primary-color-light); border-color: var(--primary-color-light);">3</div>
                    <h4>Fine-Tune Parameters</h4>
                    <p>Adjust sensitivities, FOV, color profiles, smoothing, and hundreds of other options.</p>
                </div>
                <div class="step-card" style="background-color: #fff; color: #333;">
                     <div class="step-number" style="color: var(--primary-color-light); border-color: var(--primary-color-light);">4</div>
                    <h4>Export Your Profile</h4>
                    <p>Download your unique configuration file compatible with the PrecisionForge example engine.</p>
                </div>
            </div>
        </div>
    </section>


    <section id="testimonials" class="section">
        <div class="container">
            <h2 class="section-title">What Users Say</h2>
            <div class="testimonials-slider">
                <div class="testimonial-card">
                    <p>"The level of control is insane! I tailored an assistant perfect for my reaction time and playstyle. The simulation tools are a game-changer."</p>
                    <div class="author">- AlphaTester_01</div>
                </div>
                <div class="testimonial-card">
                    <p>"Finally, a platform that lets me experiment with aiming dynamics without complex coding. The Forge UI is intuitive and powerful."</p>
                    <div class="author">- ProSimUserX</div>
                </div>
                 <div class="testimonial-card">
                    <p>"Being able to visualize how different settings affect aim in the simulator has genuinely improved my understanding of mechanics."</p>
                    <div class="author">- DevInsightY</div>
                </div>
            </div>
        </div>
    </section>

    <footer>
        <div class="container">
            <div class="footer-cta">
                <h2>Ready to Forge Your Edge?</h2>
                <a href="/forge" class="cta-button">Access The Forge (Free)</a>
            </div>
            <div class="ethical-reminder">
                <p><strong>Ethical Use Reminder:</strong> PrecisionForge is designed for simulation, research, and personal skill enhancement in offline or custom environments. Use of profiles generated by this platform in public online multiplayer games may violate Terms of Service and is strongly discouraged. Users are solely responsible for how they use profiles generated by this platform and any example engine code provided.</p>
            </div>
            <div class="copyright">
                &copy; <span id="currentYear"></span> PrecisionForge. All Rights Reserved (Concept Project).
            </div>
        </div>
    </footer>

    <script>
        // Theme Toggle
        const themeToggle = document.getElementById('themeToggle');
        const body = document.body;
        const currentTheme = localStorage.getItem('theme') || 'light';
        body.classList.add(currentTheme + '-theme');
        if (currentTheme === 'dark') {
            themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
            // Adjust section that needs to stay light
            const howItWorksSection = document.getElementById('how-it-works');
            if(howItWorksSection) {
                 howItWorksSection.style.backgroundColor = 'var(--bg-color-dark)'; // Match dark theme bg
                 const innerContainer = howItWorksSection.querySelector('.dark-theme'); // This was a mistake in HTML, should be light-theme
                 if(innerContainer) {
                    // innerContainer.classList.remove('dark-theme');
                    // innerContainer.classList.add('light-theme');
                    // // Manually set styles for children if needed
                 }
            }
        } else {
             themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
        }


        themeToggle.addEventListener('click', () => {
            body.classList.toggle('dark-theme');
            body.classList.toggle('light-theme');
            let theme = 'light';
            if (body.classList.contains('dark-theme')) {
                theme = 'dark';
                themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
            } else {
                themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
            }
            localStorage.setItem('theme', theme);
             // Re-apply specific section styling if needed
            if (theme === 'dark') {
                const howItWorksSection = document.getElementById('how-it-works');
                 if(howItWorksSection) howItWorksSection.style.backgroundColor = 'var(--bg-color-dark)';
            } else {
                 const howItWorksSection = document.getElementById('how-it-works');
                 if(howItWorksSection) howItWorksSection.style.backgroundColor = 'var(--card-bg-light)';
            }
        });
        document.getElementById('currentYear').textContent = new Date().getFullYear();
    </script>
</body>
</html>
"""

# Forge UI HTML (incorporating user's provided template and adding tabs/simulation)
FORGE_UI_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PrecisionForge - The Forge</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color-light: #f0f4f8; --text-color-light: #333; --primary-color-light: #3498db; --card-bg-light: #ffffff; --border-color-light: #d1d8e0; --input-bg-light: #e9eff5; --input-border-light: #b0c4de;
            --bg-color-dark: #2c3e50; --text-color-dark: #ecf0f1; --primary-color-dark: #5dade2; --card-bg-dark: #34495e; --border-color-dark: #4a627a; --input-bg-dark: #405266; --input-border-dark: #5a728a;
        }
        body { font-family: 'Segoe UI', sans-serif; margin: 0; padding: 0; transition: background-color 0.3s, color 0.3s; }
        .light-theme { background-color: var(--bg-color-light); color: var(--text-color-light); }
        .dark-theme { background-color: var(--bg-color-dark); color: var(--text-color-dark); }
        
        .forge-container { display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 220px; background-color: var(--card-bg-light); padding: 20px; border-right: 1px solid var(--border-color-light); overflow-y: auto;}
        .dark-theme .sidebar { background-color: var(--card-bg-dark); border-right-color: var(--border-color-dark); }
        .sidebar h2 { font-size: 1.5em; color: var(--primary-color-light); margin-top: 0; margin-bottom: 20px; }
        .dark-theme .sidebar h2 { color: var(--primary-color-dark); }
        .sidebar ul { list-style: none; padding: 0; margin: 0; }
        .sidebar ul li a {
            display: block; padding: 12px 15px; text-decoration: none;
            border-radius: 6px; margin-bottom: 8px; transition: background-color 0.2s, color 0.2s;
            font-weight: 500;
        }
        .light-theme .sidebar ul li a { color: #455a64; }
        .dark-theme .sidebar ul li a { color: #bdc3c7; }
        .light-theme .sidebar ul li a:hover { background-color: #e0e6eb; color: var(--primary-color-light); }
        .dark-theme .sidebar ul li a:hover { background-color: #4a627a; color: var(--primary-color-dark); }
        .light-theme .sidebar ul li a.active { background-color: var(--primary-color-light); color: white; }
        .dark-theme .sidebar ul li a.active { background-color: var(--primary-color-dark); color: var(--bg-color-dark); }

        .main-content { flex-grow: 1; padding: 25px; overflow-y: auto; }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.5s; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        h3 { font-size: 1.8em; margin-bottom: 20px; color: var(--primary-color-light); border-bottom: 2px solid var(--primary-color-light); padding-bottom: 10px;}
        .dark-theme h3 { color: var(--primary-color-dark); border-bottom-color: var(--primary-color-dark); }
        
        .form-section { margin-bottom: 25px; padding: 20px; background-color: var(--card-bg-light); border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .dark-theme .form-section { background-color: var(--card-bg-dark); box-shadow: 0 2px 10px rgba(0,0,0,0.15); }
        
        .form-group { margin-bottom: 18px; display: flex; flex-wrap: wrap; align-items: center; }
        .form-group label { display: block; min-width: 180px; font-weight: 600; margin-bottom: 5px; margin-right:15px; flex-shrink: 0;}
        .form-group input[type="text"],
        .form-group input[type="number"],
        .form-group input[type="color"],
        .form-group select,
        .form-group textarea {
            flex-grow: 1;
            padding: 10px;
            border: 1px solid var(--input-border-light);
            border-radius: 5px;
            background-color: var(--input-bg-light);
            transition: border-color 0.2s;
            min-width: 150px;
        }
        .dark-theme .form-group input[type="text"],
        .dark-theme .form-group input[type="number"],
        .dark-theme .form-group input[type="color"],
        .dark-theme .form-group select,
        .dark-theme .form-group textarea {
            border-color: var(--input-border-dark);
            background-color: var(--input-bg-dark);
            color: var(--text-color-dark);
        }
        .form-group input[type="text"]:focus,
        .form-group input[type="number"]:focus,
        .form-group input[type="color"]:focus,
        .form-group select:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: var(--primary-color-light);
            box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.3);
        }
        .dark-theme .form-group input[type="text"]:focus,
        .dark-theme .form-group input[type="number"]:focus,
        .dark-theme .form-group input[type="color"]:focus,
        .dark-theme .form-group select:focus,
        .dark-theme .form-group textarea:focus {
             border-color: var(--primary-color-dark);
             box-shadow: 0 0 0 2px rgba(93, 173, 226, 0.3);
        }

        .form-group input[type="checkbox"] { margin-right: 8px; transform: scale(1.2); }
        .form-group .slider-value { margin-left: 15px; font-weight: bold; min-width: 40px; text-align: right; }
        input[type="range"] { flex-grow: 1; -webkit-appearance: none; height: 8px; border-radius: 4px; background: #ddd; outline: none; cursor: pointer; }
        .dark-theme input[type="range"] { background: #555; }
        input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; width: 20px; height: 20px; background: var(--primary-color-light); border-radius: 50%; }
        .dark-theme input[type="range"]::-webkit-slider-thumb { background: var(--primary-color-dark); }

        .button, button {
            background-color: var(--primary-color-light); color: white;
            padding: 10px 20px; border: none; border-radius: 5px;
            cursor: pointer; font-weight: bold; transition: background-color 0.2s;
            margin-right: 10px;
        }
        .dark-theme .button, .dark-theme button { background-color: var(--primary-color-dark); }
        .button:hover, button:hover { filter: brightness(1.1); }
        .button.secondary { background-color: #7f8c8d; }
        .dark-theme .button.secondary { background-color: #95a5a6; }


        #simulationCanvas { border: 1px solid var(--border-color-light); margin-bottom: 15px; background-color: #fdfdfd; }
        .dark-theme #simulationCanvas { border-color: var(--border-color-dark); background-color: #222f3e; }
        .charts-container { display: flex; flex-wrap: wrap; gap: 20px; }
        .chart-wrapper { flex: 1 1 45%; min-width: 300px; background: var(--card-bg-light); padding:15px; border-radius:8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);}
        .dark-theme .chart-wrapper { background: var(--card-bg-dark); box-shadow: 0 2px 10px rgba(0,0,0,0.15); }

        .theme-toggle-forge {
            position: absolute; top: 20px; right: 30px;
            cursor: pointer; font-size: 1.5em; z-index: 100;
            background: none; border: none; padding: 5px;
        }
        .light-theme .theme-toggle-forge { color: var(--text-color-light); }
        .dark-theme .theme-toggle-forge { color: var(--text-color-dark); }

        /* User's original styles from HTML_TEMPLATE, adapted for theme and consistency */
        .toggle-3d { /* Simplified toggle */
            appearance: none; width: 50px; height: 26px; border-radius: 13px;
            background: #ccc; border: 1px solid #bbb;
            cursor: pointer; vertical-align: middle; margin-right: 10px;
            position: relative; transition: background-color 0.3s;
        }
        .dark-theme .toggle-3d { background: #555; border-color: #444; }
        .toggle-3d::before {
            content: ''; position: absolute; width: 22px; height: 22px;
            border-radius: 50%; background: white; top: 2px; left: 2px;
            transition: transform 0.3s;
        }
        .dark-theme .toggle-3d::before { background: #ddd; }
        .toggle-3d:checked { background: var(--primary-color-light); border-color: var(--primary-color-light); }
        .dark-theme .toggle-3d:checked { background: var(--primary-color-dark); border-color: var(--primary-color-dark); }
        .toggle-3d:checked::before { transform: translateX(24px); }

        /* To match the output span from user's HTML */
        .output-value { display: inline-block; width: 60px; text-align: right; font-weight: bold; color: var(--primary-color-light); font-size: 1em; vertical-align: middle;}
        .dark-theme .output-value { color: var(--primary-color-dark); }

    </style>
</head>
<body class="light-theme">
    <button id="themeToggleForge" class="theme-toggle-forge" title="Toggle Theme"><i class="fas fa-moon"></i></button>
    <div class="forge-container">
        <aside class="sidebar">
            <h2><i class="fas fa-tools"></i> The Forge</h2>
            <ul>
                <li><a href="#detectionCore" class="tab-link active"><i class="fas fa-eye"></i> Detection Core</a></li>
                <li><a href="#aimbotModule" class="tab-link"><i class="fas fa-crosshairs"></i> Aimbot Module</a></li>
                <li><a href="#triggerbotModule" class="tab-link"><i class="fas fa-bolt"></i> Triggerbot Module</a></li>
                <li><a href="#uiOverlay" class="tab-link"><i class="fas fa-layer-group"></i> UI Overlay</a></li>
                <li><a href="#simulation" class="tab-link"><i class="fas fa-flask"></i> Simulation</a></li>
                <li><a href="#profileHub" class="tab-link"><i class="fas fa-save"></i> Profile Hub</a></li>
            </ul>
        </aside>

        <main class="main-content">
            <form id="settingsForm">

            <!-- Detection Core Tab -->
            <div id="detectionCore" class="tab-content active">
                <h3><i class="fas fa-eye"></i> Detection Core Configuration</h3>
                <div class="form-section">
                    <div class="form-group">
                        <label for="detectionMethod">Detection Method:</label>
                        <select id="detectionMethod" name="detection_core.method">
                            <option value="color">Color-Based</option>
                            <option value="pattern_placeholder" disabled>Pixel Pattern (Placeholder)</option>
                            <option value="ai_placeholder" disabled>AI Model (Placeholder)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="primaryTargetColor">Primary Target Color (Hex):</label>
                        <input type="color" id="primaryTargetColor" name="detection_core.primary_target_color_hex" value="#FFFF00">
                    </div>
                    <div class="form-group">
                        <label for="colorToleranceR">Color Tolerance (Red):</label>
                        <input type="range" id="colorToleranceR" name="detection_core.color_tolerance_r" min="0" max="50" value="15" oninput="this.nextElementSibling.textContent=this.value">
                        <span class="slider-value output-value">15</span>
                    </div>
                     <div class="form-group">
                        <label for="colorToleranceG">Color Tolerance (Green):</label>
                        <input type="range" id="colorToleranceG" name="detection_core.color_tolerance_g" min="0" max="50" value="15" oninput="this.nextElementSibling.textContent=this.value">
                        <span class="slider-value output-value">15</span>
                    </div>
                     <div class="form-group">
                        <label for="colorToleranceB">Color Tolerance (Blue):</label>
                        <input type="range" id="colorToleranceB" name="detection_core.color_tolerance_b" min="0" max="50" value="15" oninput="this.nextElementSibling.textContent=this.value">
                        <span class="slider-value output-value">15</span>
                    </div>
                    <div class="form-group">
                        <label for="minPixelSize">Min. Pixel Size for Detection:</label>
                        <input type="number" id="minPixelSize" name="detection_core.min_pixel_size" min="1" max="100" value="5">
                    </div>
                    <div class="form-group">
                        <label for="fovShape">Scan Area Shape:</label>
                        <select id="fovShape" name="detection_core.fov_shape">
                            <option value="circle">Circle</option>
                            <option value="square">Square</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="fovSizePercent">Scan Area Size (% of screen shorter_dim):</label>
                        <input type="range" id="fovSizePercent" name="detection_core.fov_size_percent" min="5" max="100" value="20" step="1" oninput="this.nextElementSibling.textContent=this.value + '%'">
                        <span class="slider-value output-value">20%</span>
                    </div>
                    <div class="form-group">
                        <label for="scanRateFps">Target Scan Rate (FPS):</label>
                        <input type="range" id="scanRateFps" name="detection_core.scan_rate_fps" min="10" max="240" value="60" step="5" oninput="this.nextElementSibling.textContent=this.value">
                        <span class="slider-value output-value">60</span>
                    </div>
                </div>
            </div>

            <!-- Aimbot Module Tab -->
            <div id="aimbotModule" class="tab-content">
                <h3><i class="fas fa-crosshairs"></i> Aimbot Module Configuration</h3>
                <div class="form-section">
                     <div class="form-group">
                        <label for="aimbotEnabled">Aimbot Enabled:</label>
                        <input class="toggle-3d" type="checkbox" id="aimbotEnabled" name="aimbot_module.enabled" value="true">
                    </div>
                    <div class="form-group">
                        <label for="aimbotAlwaysOn">Aimbot Always On (no key needed):</label>
                        <input class="toggle-3d" type="checkbox" id="aimbotAlwaysOn" name="aimbot_module.always_on" value="true">
                    </div>
                    <div class="form-group">
                        <label for="aimbotActivationKey">Activation Key/Button:</label>
                        <select id="aimbotActivationKey" name="aimbot_module.activation_key">
                            <option value="mouse1">Left Mouse Button</option>
                            <option value="mouse2">Right Mouse Button</option>
                            <option value="mouse3">Middle Mouse Button</option>
                            <option value="key_shift">Shift Key</option>
                            <option value="key_ctrl">Ctrl Key</option>
                        </select>
                    </div>
                     <div class="form-group">
                        <label for="aimbotFovPixels">Aimbot FOV (pixels around target):</label>
                        <input type="range" id="aimbotFovPixels" name="aimbot_module.fov_pixels" min="2" max="200" step="1" value="{{ aimbot_module.fov_pixels | default(50) }}" oninput="this.nextElementSibling.textContent=this.value">
                        <span class="output-value">{{ aimbot_module.fov_pixels | default(50) }}</span>
                    </div>
                    <div class="form-group">
                        <label for="aimbotTargetingPriority">Targeting Priority:</label>
                        <select id="aimbotTargetingPriority" name="aimbot_module.targeting_priority">
                            <option value="closest_to_crosshair">Closest to Crosshair</option>
                            <option value="lowest_health_placeholder" disabled>Lowest Health (Placeholder)</option>
                            <option value="head">Head (via Y-Offset)</option>
                            <option value="body">Body/Torso (via Y-Offset)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="aimbotAimLocationOffsetY">Aim Location Y-Offset (Head/Body):</label>
                        <input type="range" id="aimbotAimLocationOffsetY" name="aimbot_module.aim_location_offset_y" min="-50" max="50" value="-5" step="1" oninput="this.nextElementSibling.textContent=this.value">
                        <span class="slider-value output-value">-5</span>
                    </div>
                     <div class="form-group">
                        <label for="aimbotSmoothingFactor">Smoothing Factor:</label>
                        <input type="range" id="aimbotSmoothingFactor" name="aimbot_module.smoothing_factor" min="0.1" max="1.0" value="0.5" step="0.05" oninput="this.nextElementSibling.textContent=parseFloat(this.value).toFixed(2)">
                        <span class="slider-value output-value">0.50</span>
                    </div>
                    <div class="form-group">
                        <label for="aimbotLeftSensitivity">Left Mouse (ADS) Sensitivity Multiplier:</label>
                        <input type="range" id="aimbotLeftSensitivity" name="aimbot_module.sensitivity_multiplier_left" min="0.01" max="2.0" step="0.01" value="0.25" oninput="this.nextElementSibling.textContent=parseFloat(this.value).toFixed(2)">
                        <span class="slider-value output-value">0.25</span>
                    </div>
                    <div class="form-group">
                        <label for="aimbotRightSensitivity">Right Mouse (Hip) Sensitivity Multiplier:</label>
                        <input type="range" id="aimbotRightSensitivity" name="aimbot_module.sensitivity_multiplier_right" min="0.01" max="2.0" step="0.01" value="0.25" oninput="this.nextElementSibling.textContent=parseFloat(this.value).toFixed(2)">
                        <span class="slider-value output-value">0.25</span>
                    </div>
                    <div class="form-group">
                        <label for="aimbotDynamicSensEnabled">Dynamic Sensitivity (Reduce for small adjustments):</label>
                        <input class="toggle-3d" type="checkbox" id="aimbotDynamicSensEnabled" name="aimbot_module.dynamic_sensitivity_enabled" value="true" checked>
                    </div>
                     <div class="form-group">
                        <label for="aimbotDynamicSensThreshold">Dyn. Sens. Threshold (pixels):</label>
                        <input type="range" id="aimbotDynamicSensThreshold" name="aimbot_module.dynamic_sensitivity_threshold" min="1" max="20" value="5" step="1" oninput="this.nextElementSibling.textContent=this.value">
                        <span class="slider-value output-value">5</span>
                    </div>
                     <div class="form-group">
                        <label for="aimbotDynamicSensReduction">Dyn. Sens. Reduction Factor:</label>
                        <input type="range" id="aimbotDynamicSensReduction" name="aimbot_module.dynamic_sensitivity_reduction" min="0.1" max="0.9" value="0.5" step="0.05" oninput="this.nextElementSibling.textContent=parseFloat(this.value).toFixed(2)">
                        <span class="slider-value output-value">0.50</span>
                    </div>
                </div>
            </div>

            <!-- Triggerbot Module Tab -->
            <div id="triggerbotModule" class="tab-content">
                <h3><i class="fas fa-bolt"></i> Triggerbot Module Configuration</h3>
                <div class="form-section">
                     <div class="form-group">
                        <label for="triggerbotEnabled">Triggerbot Enabled:</label>
                        <input class="toggle-3d" type="checkbox" id="triggerbotEnabled" name="triggerbot_module.enabled" value="true">
                    </div>
                    <div class="form-group">
                        <label for="triggerbotActivationKey">Activation Key/Button:</label>
                        <select id="triggerbotActivationKey" name="triggerbot_module.activation_key">
                            <option value="mouse1">Left Mouse Button (Hold)</option>
                            <option value="mouse2">Right Mouse Button (Hold)</option>
                            <option value="always_on_crosshair">Always On (when enemy in crosshair)</option>
                            <option value="key_alt">Alt Key (Hold)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="triggerbotDelayMs">Delay Before Firing (ms):</label>
                        <input type="range" id="triggerbotDelayMs" name="triggerbot_module.delay_ms" min="0" max="500" value="100" step="10" oninput="this.nextElementSibling.textContent=this.value + ' ms'">
                        <span class="slider-value output-value">100 ms</span>
                    </div>
                     <div class="form-group">
                        <label for="triggerbotSelectedGun">Gun Profile (for Fire Interval):</label>
                        <select id="triggerbotSelectedGun" name="triggerbot_module.selected_gun">
                          <option value="Vandel">Vandel</option>
                          <option value="OP">OP</option>
                          <option value="Sheriff">Sheriff</option>
                          <option value="Shotgun">Shotgun</option>
                          <option value="Custom">Custom</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="triggerbotFireIntervalMs">Custom Fire Interval (ms, if 'Custom' gun):</label>
                        <input type="number" id="triggerbotFireIntervalMs" name="triggerbot_module.fire_interval_ms" min="10" max="5000" value="200">
                         <span class="output-value">(auto from gun)</span>
                    </div>
                    <div class="form-group">
                        <label for="triggerbotFovPixels">Triggerbot Pixel Size (crosshair area):</label>
                        <input type="range" id="triggerbotFovPixels" name="triggerbot_module.fov_pixels" min="1" max="20" step="1" value="4" oninput="this.nextElementSibling.textContent=this.value">
                        <span class="output-value">4</span>
                    </div>
                    <div class="form-group">
                        <label for="triggerbotShootWhileMoving">Shoot While Moving:</label>
                        <input class="toggle-3d" type="checkbox" id="triggerbotShootWhileMoving" name="triggerbot_module.shoot_while_moving" value="true">
                    </div>
                </div>
            </div>

            <!-- UI Overlay Tab -->
            <div id="uiOverlay" class="tab-content">
                <h3><i class="fas fa-layer-group"></i> UI Overlay Designer (JSON Config)</h3>
                <div class="form-section">
                    <div class="form-group">
                        <label for="uiOverlayEnabled">Enable Custom UI Overlay:</label>
                        <input class="toggle-3d" type="checkbox" id="uiOverlayEnabled" name="ui_overlay_designer.enabled" value="true">
                    </div>
                    <div class="form-group">
                        <label for="uiOverlayConfigJson">Overlay Elements JSON:</label>
                        <textarea id="uiOverlayConfigJson" name="ui_overlay_designer.config_json" rows="10" placeholder='Example:&#10;[&#10;  { "type": "text", "content": "Aimbot: {status}", "x": 10, "y": 10, "color": "green" },&#10;  { "type": "rect", "x_bind": "target_x", "y_bind": "target_y", "w": 20, "h": 20, "color": "red", "condition": "target_visible" }&#10;]'></textarea>
                    </div>
                    <p><small>Define UI elements like text, rectangles, or circles. Use placeholders like <code>{status}</code> or bind to simulation variables. This is a conceptual editor.</small></p>
                </div>
            </div>

            <!-- Simulation Tab -->
            <div id="simulation" class="tab-content">
                <h3><i class="fas fa-flask"></i> Simulation & Testing Environment</h3>
                <div class="form-section">
                    <h4>2D Dummy Target Simulation</h4>
                    <canvas id="simulationCanvas" width="600" height="300"></canvas>
                    <button type="button" id="runSimulationBtn">Run Simulation</button>
                    <button type="button" id="stopSimulationBtn">Stop Simulation</button>
                    <p id="simStatus">Status: Idle</p>
                </div>
                <div class="form-section">
                    <h4>Performance Metrics</h4>
                    <div id="metricsPlaceholder" style="text-align:center; padding: 20px 0;">Click "Run Simulation" to see metrics.</div>
                    <div class="charts-container" id="chartsContainer" style="display:none;">
                        <div class="chart-wrapper"><canvas id="timeToTargetChart"></canvas></div>
                        <div class="chart-wrapper"><canvas id="accuracyChart"></canvas></div>
                        <div class="chart-wrapper"><canvas id="reactionTimeChart"></canvas></div>
                        <div class="chart-wrapper"><canvas id="smoothnessChart"></canvas></div>
                    </div>
                </div>
            </div>

            <!-- Profile Hub Tab -->
            <div id="profileHub" class="tab-content">
                <h3><i class="fas fa-save"></i> Profile Hub & Downloads</h3>
                 <div class="form-section">
                    <h4>Manage Configuration</h4>
                    <button type="button" id="saveCurrentConfigBtn"><i class="fas fa-sync-alt"></i> Update & Save Current Settings</button>
                    <p id="saveStatus" style="margin-top:10px; font-style: italic;"></p>
                 </div>
                <div class="form-section">
                    <h4>Download</h4>
                    <p>Download your current configuration or the example engine code.</p>
                    <a href="/download/profile" class="button" id="downloadProfileBtn"><i class="fas fa-file-download"></i> Download Profile (.pfprofile)</a>
                    <a href="/download/engine_example" class="button secondary"><i class="fas fa-cogs"></i> Download Example Engine (.zip)</a>
                </div>
                <div class="form-section">
                    <h4>Load Profile (Conceptual)</h4>
                    <input type="file" id="loadProfileInput" accept=".pfprofile" style="display:none;">
                    <button type="button" id="loadProfileBtn"><i class="fas fa-file-upload"></i> Load Profile from File</button>
                    <p><small>This feature would allow you to load a previously saved .pfprofile file to restore settings.</small></p>
                </div>
            </div>
            </form> <!-- End of settingsForm -->
        </main>
    </div>

    <script>
        // --- Global State & Utility ---
        let currentForgeConfig = {{ initial_config | tojson }};
        let simInterval = null;
        let charts = {};

        // --- Theme Toggle for Forge UI ---
        const themeToggleForge = document.getElementById('themeToggleForge');
        const bodyForge = document.body;
        function applyForgeTheme(theme) {
            bodyForge.classList.remove('light-theme', 'dark-theme');
            bodyForge.classList.add(theme + '-theme');
            themeToggleForge.innerHTML = (theme === 'dark') ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
            localStorage.setItem('forgeTheme', theme);
            // If charts exist, update their options for theme
            Object.values(charts).forEach(chart => {
                if (chart && chart.options) {
                    const isDark = theme === 'dark';
                    const gridColor = isDark ? 'rgba(255, 255, 255, 0.2)' : 'rgba(0, 0, 0, 0.1)';
                    const ticksColor = isDark ? '#ecf0f1' : '#333';
                    const titleColor = isDark ? '#ecf0f1' : '#333';
                    if (chart.options.scales) {
                        Object.values(chart.options.scales).forEach(axis => {
                            if(axis.grid) axis.grid.color = gridColor;
                            if(axis.ticks) axis.ticks.color = ticksColor;
                        });
                    }
                    if(chart.options.plugins && chart.options.plugins.legend) chart.options.plugins.legend.labels.color = ticksColor;
                    if(chart.options.plugins && chart.options.plugins.title) chart.options.plugins.title.color = titleColor;
                    chart.update();
                }
            });
        }
        themeToggleForge.addEventListener('click', () => {
            const newTheme = bodyForge.classList.contains('dark-theme') ? 'light' : 'dark';
            applyForgeTheme(newTheme);
        });
        applyForgeTheme(localStorage.getItem('forgeTheme') || 'light');


        // --- Tab Navigation ---
        const tabLinks = document.querySelectorAll('.sidebar .tab-link');
        const tabContents = document.querySelectorAll('.main-content .tab-content');

        tabLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const targetId = link.getAttribute('href').substring(1);

                tabLinks.forEach(l => l.classList.remove('active'));
                link.classList.add('active');

                tabContents.forEach(content => {
                    content.classList.remove('active');
                    if (content.id === targetId) {
                        content.classList.add('active');
                    }
                });
            });
        });
        
        // --- Form Population & Auto-Update ---
        const form = document.getElementById('settingsForm');

        function populateForm(config) {
            for (const key in config) {
                if (typeof config[key] === 'object' && config[key] !== null) {
                    for (const subKey in config[key]) {
                        const inputName = `${key}.${subKey}`;
                        const inputElement = form.elements[inputName];
                        if (inputElement) {
                            if (inputElement.type === 'checkbox') {
                                inputElement.checked = config[key][subKey];
                            } else if (inputElement.type === 'range') {
                                inputElement.value = config[key][subKey];
                                if (inputElement.nextElementSibling && inputElement.nextElementSibling.classList.contains('output-value')) {
                                     // Special formatting for range outputs
                                    if (inputName === "detection_core.fov_size_percent") inputElement.nextElementSibling.textContent = config[key][subKey] + '%';
                                    else if (inputName === "triggerbot_module.delay_ms") inputElement.nextElementSibling.textContent = config[key][subKey] + ' ms';
                                    else if (inputName.includes("sensitivity") || inputName.includes("smoothing_factor") || inputName.includes("reduction")) inputElement.nextElementSibling.textContent = parseFloat(config[key][subKey]).toFixed(2);
                                    else inputElement.nextElementSibling.textContent = config[key][subKey];
                                }
                            } else if (inputElement.tagName === 'TEXTAREA') {
                                inputElement.value = typeof config[key][subKey] === 'string' ? config[key][subKey] : JSON.stringify(config[key][subKey], null, 2);
                            }
                            else {
                                inputElement.value = config[key][subKey];
                            }
                        }
                    }
                }
            }
            // Update dependent UI like triggerbot fire interval display
            updateTriggerbotFireIntervalDisplay();
        }
        
        function collectFormData() {
            const formData = new FormData(form);
            const newConfig = JSON.parse(JSON.stringify(currentForgeConfig)); // Deep copy

            formData.forEach((value, key) => {
                const keys = key.split('.');
                let current = newConfig;
                keys.forEach((k, index) => {
                    if (index === keys.length - 1) {
                        const inputElement = form.elements[key];
                        if(inputElement && inputElement.type === 'checkbox') {
                             current[k] = inputElement.checked; // Use .checked for checkboxes
                        } else if (inputElement && (inputElement.type === 'number' || inputElement.type === 'range')) {
                            current[k] = parseFloat(value) || 0;
                        } else {
                            current[k] = value;
                        }
                    } else {
                        if (!current[k]) current[k] = {};
                        current = current[k];
                    }
                });
            });
            // Handle unchecked checkboxes (FormData doesn't include them)
            form.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                if (!cb.checked) {
                    const keys = cb.name.split('.');
                    let current = newConfig;
                    keys.forEach((k, index) => {
                         if (index === keys.length - 1) current[k] = false;
                         else { if(!current[k]) current[k] = {}; current = current[k]; }
                    });
                }
            });
            return newConfig;
        }

        async function updateSettingsOnServer() {
            currentForgeConfig = collectFormData();
            // console.log("Updating server with config:", currentForgeConfig);
            try {
                const response = await fetch('/api/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(currentForgeConfig)
                });
                const result = await response.json();
                if (result.success) {
                    document.getElementById('saveStatus').textContent = 'Settings saved successfully at ' + new Date().toLocaleTimeString();
                } else {
                    document.getElementById('saveStatus').textContent = 'Error saving settings.';
                }
            } catch (error) {
                console.error("Error updating settings:", error);
                document.getElementById('saveStatus').textContent = 'Error: Could not connect to server.';
            }
        }
        
        // Add event listeners to form elements for auto-update
        form.querySelectorAll('input, select, textarea').forEach(el => {
            el.addEventListener('change', updateSettingsOnServer); 
            // For sliders, update on 'input' for live feedback on display value, but server update on 'change'
            if (el.type === 'range') {
                el.addEventListener('input', () => {
                    const displayEl = el.nextElementSibling;
                    if (displayEl && displayEl.classList.contains('output-value')) {
                         if (el.name === "detection_core.fov_size_percent") displayEl.textContent = el.value + '%';
                         else if (el.name === "triggerbot_module.delay_ms") displayEl.textContent = el.value + ' ms';
                         else if (el.name.includes("sensitivity") || el.name.includes("smoothing_factor") || el.name.includes("reduction")) displayEl.textContent = parseFloat(el.value).toFixed(2);
                         else displayEl.textContent = el.value;
                    }
                });
            }
        });
        
        document.getElementById('saveCurrentConfigBtn').addEventListener('click', updateSettingsOnServer);

        // Triggerbot gun settings logic
        const selectedGunElement = document.getElementById('triggerbotSelectedGun');
        const fireIntervalMsElement = document.getElementById('triggerbotFireIntervalMs');
        const fireIntervalDisplayElement = fireIntervalMsElement.nextElementSibling;

        function updateTriggerbotFireIntervalDisplay() {
            const selectedGun = selectedGunElement.value;
            if (selectedGun === "Custom") {
                fireIntervalMsElement.disabled = false;
                fireIntervalDisplayElement.textContent = "(user defined)";
            } else {
                fireIntervalMsElement.disabled = true;
                const gunInterval = currentForgeConfig.gun_settings[selectedGun] || 0.25; // Default if not found
                fireIntervalMsElement.value = gunInterval * 1000; // Convert s to ms
                fireIntervalDisplayElement.textContent = `(${gunInterval * 1000} ms from ${selectedGun})`;
                // Also update the config object directly for this derived value
                if(currentForgeConfig.triggerbot_module) {
                    currentForgeConfig.triggerbot_module.fire_interval_ms = gunInterval * 1000;
                }
            }
        }
        selectedGunElement.addEventListener('change', () => {
            updateTriggerbotFireIntervalDisplay();
            updateSettingsOnServer(); // Update server as gun choice affects fire_interval_ms
        });


        // --- Simulation Canvas Logic ---
        const canvas = document.getElementById('simulationCanvas');
        const ctx = canvas.getContext('2d');
        const runSimBtn = document.getElementById('runSimulationBtn');
        const stopSimBtn = document.getElementById('stopSimulationBtn');
        const simStatusEl = document.getElementById('simStatus');
        let targets = [];
        let crosshair = { x: canvas.width / 2, y: canvas.height / 2, size: 10, detectedTarget: null };

        function drawTarget(target) {
            ctx.beginPath();
            ctx.arc(target.x, target.y, target.radius, 0, Math.PI * 2);
            ctx.fillStyle = target.isHit ? 'lightgreen' : (target.isAimedAt ? 'orange' : target.color);
            ctx.fill();
            ctx.strokeStyle = 'darkred';
            if(target.isLocked) {
                ctx.lineWidth = 2;
                ctx.strokeRect(target.x - target.radius - 2, target.y - target.radius - 2, target.radius*2 + 4, target.radius*2 + 4);
                ctx.lineWidth = 1;
            }
        }

        function drawCrosshair() {
            const x = crosshair.x;
            const y = crosshair.y;
            const size = crosshair.size;
            ctx.strokeStyle = currentForgeConfig.aimbot_module.enabled && crosshair.detectedTarget ? 'lime' : 'red';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(x - size, y); ctx.lineTo(x + size, y);
            ctx.moveTo(x, y - size); ctx.lineTo(x, y + size);
            ctx.stroke();
            
            // Draw aimbot FOV (from detection core config)
            if (currentForgeConfig.aimbot_module.enabled) {
                const fovRadius = (currentForgeConfig.detection_core.fov_size_percent / 100) * (Math.min(canvas.width, canvas.height) / 2);
                ctx.beginPath();
                ctx.arc(x, y, fovRadius, 0, Math.PI * 2);
                ctx.strokeStyle = 'rgba(0, 255, 0, 0.3)';
                ctx.stroke();
            }
        }
        
        function updateSimulation() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // Simple target movement
            targets.forEach(target => {
                target.x += target.vx;
                target.y += target.vy;
                if (target.x - target.radius < 0 || target.x + target.radius > canvas.width) target.vx *= -1;
                if (target.y - target.radius < 0 || target.y + target.radius > canvas.height) target.vy *= -1;
                
                target.isAimedAt = false; // Reset
                target.isLocked = false;  // Reset
            });

            // Simple Aimbot Logic (visual only for canvas)
            crosshair.detectedTarget = null;
            let closestTarget = null;
            let minDist = Infinity;
            const aimFovRadius = (currentForgeConfig.detection_core.fov_size_percent / 100) * (Math.min(canvas.width, canvas.height) / 2);

            targets.forEach(target => {
                const dist = Math.sqrt((target.x - crosshair.x)**2 + (target.y - crosshair.y)**2);
                if (dist < aimFovRadius && dist < minDist) {
                    minDist = dist;
                    closestTarget = target;
                }
            });
            
            if (currentForgeConfig.aimbot_module.enabled && closestTarget) {
                crosshair.detectedTarget = closestTarget;
                closestTarget.isAimedAt = true; // Visual cue
                // Simulate aiming movement (move crosshair towards target)
                const aimSpeed = currentForgeConfig.aimbot_module.smoothing_factor * 10; // Adjust for visual speed
                const dx = closestTarget.x - crosshair.x;
                const dy = closestTarget.y - crosshair.y;
                const distToTarget = Math.sqrt(dx*dx + dy*dy);

                if (distToTarget > 1) { // Keep moving if not on target
                    crosshair.x += (dx / distToTarget) * Math.min(aimSpeed, distToTarget);
                    crosshair.y += (dy / distToTarget) * Math.min(aimSpeed, distToTarget);
                } else {
                    closestTarget.isLocked = true; // Visual cue for lock
                }
                 // Simple Triggerbot Logic (visual only for canvas)
                if (currentForgeConfig.triggerbot_module.enabled && closestTarget.isLocked) {
                    const tbFov = currentForgeConfig.triggerbot_module.fov_pixels; // This is small
                    if (Math.abs(closestTarget.x - crosshair.x) < tbFov && Math.abs(closestTarget.y - crosshair.y) < tbFov) {
                        if (!target.shotRecently) { // Avoid constant shooting visual
                             closestTarget.isHit = true; // Visual cue for hit
                             target.shotRecently = true;
                             setTimeout(() => { target.isHit = false; target.shotRecently = false; }, 500); // Reset visual
                        }
                    }
                }
            } else { // If aimbot disabled or no target, reset crosshair to center if it drifted
                const dx_home = canvas.width / 2 - crosshair.x;
                const dy_home = canvas.height / 2 - crosshair.y;
                if (Math.abs(dx_home) > 1 || Math.abs(dy_home) > 1) {
                    crosshair.x += dx_home * 0.1; // Slowly return to center
                    crosshair.y += dy_home * 0.1;
                }
            }

            targets.forEach(drawTarget);
            drawCrosshair();
        }

        runSimBtn.addEventListener('click', async () => {
            simStatusEl.textContent = "Status: Running...";
            document.getElementById('metricsPlaceholder').style.display = 'none';
            document.getElementById('chartsContainer').style.display = 'flex';

            // Initialize targets
            targets = [];
            for (let i = 0; i < 5; i++) {
                targets.push({
                    x: Math.random() * canvas.width, y: Math.random() * canvas.height,
                    vx: (Math.random() - 0.5) * 4, vy: (Math.random() - 0.5) * 4,
                    radius: 10 + Math.random() * 10, color: `hsl(${Math.random()*360}, 70%, 60%)`,
                    isHit: false, isAimedAt: false, isLocked: false, shotRecently: false
                });
            }
            crosshair.x = canvas.width / 2; crosshair.y = canvas.height / 2; // Reset crosshair

            if (simInterval) clearInterval(simInterval);
            simInterval = setInterval(updateSimulation, 1000 / 30); // 30 FPS simulation

            // Fetch mock simulation data
            try {
                const response = await fetch('/api/simulate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(currentForgeConfig)
                });
                const metrics = await response.json();
                displayMetrics(metrics);
            } catch (error) {
                console.error("Error fetching simulation metrics:", error);
                simStatusEl.textContent = "Status: Error fetching metrics.";
            }
        });

        stopSimBtn.addEventListener('click', () => {
            if (simInterval) clearInterval(simInterval);
            simInterval = null;
            simStatusEl.textContent = "Status: Stopped.";
            ctx.clearRect(0, 0, canvas.width, canvas.height); // Clear canvas
             document.getElementById('metricsPlaceholder').style.display = 'block';
             document.getElementById('chartsContainer').style.display = 'none';
        });

        // --- Metrics Display ---
        function createOrUpdateChart(chartId, label, data, type = 'line', backgroundColor = 'rgba(52, 152, 219, 0.5)', borderColor = 'rgba(52, 152, 219, 1)') {
            const ctx = document.getElementById(chartId).getContext('2d');
            const isDark = bodyForge.classList.contains('dark-theme');
            const gridColor = isDark ? 'rgba(255, 255, 255, 0.2)' : 'rgba(0, 0, 0, 0.1)';
            const ticksColor = isDark ? '#ecf0f1' : '#333';
            const titleColor = isDark ? '#ecf0f1' : '#333';

            if (charts[chartId]) {
                charts[chartId].data.labels = data.map((_, i) => i + 1);
                charts[chartId].data.datasets[0].data = data;
                charts[chartId].data.datasets[0].label = label;
                charts[chartId].update();
            } else {
                charts[chartId] = new Chart(ctx, {
                    type: type,
                    data: {
                        labels: data.map((_, i) => i + 1),
                        datasets: [{
                            label: label,
                            data: data,
                            backgroundColor: backgroundColor,
                            borderColor: borderColor,
                            borderWidth: 2,
                            tension: 0.1,
                            fill: type !== 'line' // Fill for bar/radar, not usually for line unless specified
                        }]
                    },
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        scales: {
                            y: { beginAtZero: true, grid: { color: gridColor }, ticks: { color: ticksColor } },
                            x: { grid: { color: gridColor }, ticks: { color: ticksColor } }
                        },
                        plugins: {
                            legend: { labels: { color: ticksColor } },
                            title: { display: true, text: label, color: titleColor, font: {size: 16} }
                        }
                    }
                });
            }
        }

        function displayMetrics(metrics) {
            createOrUpdateChart('timeToTargetChart', 'Time to Target (ms)', metrics.time_to_target, 'line', 'rgba(46, 204, 113, 0.5)', '#2ecc71');
            createOrUpdateChart('reactionTimeChart', 'Triggerbot Reaction Time (ms)', metrics.reaction_distribution, 'bar', 'rgba(230, 126, 34, 0.5)', '#e67e22');
            createOrUpdateChart('smoothnessChart', 'Aim Smoothness (Lower is Smoother)', metrics.smoothness_values, 'line', 'rgba(155, 89, 182, 0.5)', '#9b59b6');
            
            // For accuracy (single value), maybe a doughnut or bar chart if you want to visualize it
            const accuracyCtx = document.getElementById('accuracyChart').getContext('2d');
            const accPercent = metrics.accuracy_percent;
            if (charts['accuracyChart']) charts['accuracyChart'].destroy(); // Destroy old if exists
            charts['accuracyChart'] = new Chart(accuracyCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Hit', 'Miss'],
                    datasets: [{
                        label: 'Aim Accuracy',
                        data: [accPercent, 100 - accPercent],
                        backgroundColor: ['rgba(52, 152, 219, 0.7)', 'rgba(231, 76, 60, 0.7)'],
                        borderColor: [ '#3498db', '#e74c3c'],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'top', labels: {color: bodyForge.classList.contains('dark-theme') ? '#ecf0f1' : '#333'} },
                        title: { display: true, text: `Aim Accuracy: ${accPercent.toFixed(1)}%`, color: bodyForge.classList.contains('dark-theme') ? '#ecf0f1' : '#333', font: {size: 16} }
                    }
                }
            });
        }

        // --- Profile Load (Conceptual) ---
        document.getElementById('loadProfileBtn').addEventListener('click', () => {
            document.getElementById('loadProfileInput').click();
        });
        document.getElementById('loadProfileInput').addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    try {
                        const loadedConfig = JSON.parse(e.target.result);
                        currentForgeConfig = loadedConfig; // Update global JS config
                        populateForm(currentForgeConfig);   // Update UI
                        updateSettingsOnServer();         // Update server
                        alert('Profile loaded successfully! Settings updated.');
                    } catch (err) {
                        alert('Error loading profile: Invalid file format.');
                        console.error("Error parsing profile:", err);
                    }
                };
                reader.readAsText(file);
            }
        });

        // --- Initial Population ---
        populateForm(currentForgeConfig);
        // Initial call to set up download link correctly
        // updateDownloadLink(); // Not strictly needed if href is static and backend serves current_config

    </script>
</body>
</html>
"""

# --- Flask Routes ---

@app.route('/')
def index():
    return render_template_string(LANDING_PAGE_HTML)

@app.route('/forge')
def forge():
    # Pass the current_config to the template for initial population
    return render_template_string(FORGE_UI_HTML, initial_config=current_config)

@app.route('/api/update', methods=['POST'])
def api_update_settings():
    global current_config
    data = request.json
    if data:
        # Basic validation or transformation could happen here
        current_config.update(data) # Simple update, consider more robust merging
        # print(f"Updated config: {current_config}")
        return jsonify({"success": True, "message": "Configuration updated."})
    return jsonify({"success": False, "message": "No data received."}), 400

@app.route('/api/simulate', methods=['POST'])
def api_simulate():
    # Received config could be used to influence mock data, but for now, it's random.
    # user_config = request.json 
    
    # Generate mock metrics
    mock_metrics = {
        "time_to_target": [random.randint(50, 200) for _ in range(10)],
        "accuracy_percent": random.uniform(60.0, 95.0),
        "reaction_distribution": [random.randint(80, 300) for _ in range(10)],
        "smoothness_values": [random.uniform(0.5, 3.0) for _ in range(10)] # Lower is "smoother"
    }
    return jsonify(mock_metrics)

@app.route('/download/profile')
def download_profile():
    global current_config
    profile_json = json.dumps(current_config, indent=2)
    
    # Create an in-memory text file
    str_io = io.StringIO()
    str_io.write(profile_json)
    str_io.seek(0)
    
    mem_io = io.BytesIO()
    mem_io.write(str_io.getvalue().encode('utf-8'))
    mem_io.seek(0)
    str_io.close()

    return send_file(
        mem_io,
        mimetype='application/json',
        as_attachment=True,
        download_name='precision_forge_profile.pfprofile'
    )

@app.route('/download/engine_example')
def download_engine_example():
    global EXAMPLE_ENGINE_PYTHON_CODE
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add the Python engine code
        zf.writestr('precision_forge_example_engine.py', EXAMPLE_ENGINE_PYTHON_CODE)
        
        # Add a README
        readme_content = """
PrecisionForge - Example Engine Code
====================================

This archive contains an example Python script (`precision_forge_example_engine.py`) 
that demonstrates how a configuration profile generated by the PrecisionForge web UI 
could be used.

Requirements:
-------------
- Python 3.7+
- `mss` library (`pip install mss`)
- `pynput` library (`pip install pynput`)
- `numpy` library (`pip install numpy`)
- (For RZCONTROL) Windows OS and potentially Razer drivers with RZCONTROL present. 
  The RZCONTROL parts are highly experimental and system-dependent.

How to Use (Conceptual):
------------------------
1. Ensure you have the required libraries installed.
2. Download a `.pfprofile` file from the PrecisionForge web UI.
3. Place the `.pfprofile` file in the same directory as `precision_forge_example_engine.py`.
4. Modify `precision_forge_example_engine.py` (around the `main_example_usage` function) 
   to load your specific `.pfprofile` file.
   ```python
   # Example modification in precision_forge_example_engine.py:
   def load_profile(filepath="your_profile_name.pfprofile"):
       try:
           with open(filepath, 'r') as f:
               return json.load(f)
       except Exception as e:
           print(f"Error loading profile: {e}")
           return None # Return a default or handle error

   if __name__ == "__main__":
       print("PrecisionForge Example Engine - Standalone Runner")
       profile_data = load_profile("your_profile_name.pfprofile") # Change this filename
       if profile_data:
           engine_thread = AimbotTriggerbotEngineThread(profile_config=profile_data)
           # To start: engine_thread.start() then engine_thread.running = True (or via F1 key)
           # For testing, you might call specific methods or print config.
           print("Profile loaded. Engine thread initialized (but not started automatically).")
           print("You would typically start the thread and set its .running flag to True.")
           print("Press F1 in the console (if listeners active) to toggle the engine's running state.")
           # Example: Start the thread to enable F1 toggle.
           engine_thread.start()
           print("Engine thread listening for F1 key to toggle running state.")
           print("Ensure the game/application you are testing with is active and in focus.")
           # Keep the main thread alive if the engine thread is daemonic
           try:
               while True: time.sleep(1)
           except KeyboardInterrupt:
               print("Exiting main program.")
               if engine_thread.is_alive():
                   engine_thread.running = False # Attempt to stop it gracefully
                   # engine_thread.join(timeout=2) # Wait for thread to finish
       else:
           print("Could not load profile. Exiting.")
   ```
5. Run the script from your terminal: `python precision_forge_example_engine.py`

Disclaimer:
-----------
- This engine code is an *example* and may require significant modification and testing 
  to work correctly or safely in any specific environment.
- The RZCONTROL functionality is Windows-specific, experimental, and depends on system drivers. 
  It may not work on all systems or could be detected by anti-cheat software.
- Use responsibly and ethically. Automation in online games can violate Terms of Service.
  This tool is intended for simulation, research, and personal skill enhancement in
  offline or custom environments.
"""
        zf.writestr('README.txt', readme_content)
    memory_file.seek(0)
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='PrecisionForge_Example_Engine.zip'
    )


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 5000))
    print(f"--- PrecisionForge Server ---")
    print(f"Starting server on http://{host}:{port}")
    print(f"Access the UI at http://localhost:{port} or http://<your_ip>:{port}")
    print(f"The Forge UI is at http://localhost:{port}/forge")
    serve(app, host=host, port=port)
