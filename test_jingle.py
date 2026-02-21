#!/usr/bin/env python3
"""
Jingle Test Script
Tests jingle playback without needing Discord
"""

import os
import subprocess
import sys

def test_jingle(jingle_path=None):
    """Test playing a jingle"""
    print("\n" + "="*50)
    print("Discord Bot - Jingle Test")
    print("="*50 + "\n")
    
    # Check FFmpeg installation
    print("[*] Checking FFmpeg installation...")
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if result.returncode == 0:
            print("[✓] FFmpeg is installed\n")
        else:
            print("[✗] FFmpeg check failed\n")
            return
    except FileNotFoundError:
        print("[✗] FFmpeg not found in PATH")
        print("[*] Install FFmpeg from: https://ffmpeg.org/download.html\n")
        return
    except Exception as e:
        print(f"[✗] Error checking FFmpeg: {e}\n")
        return
    
    # Test 1: Windows built-in sound
    print("[Test 1] Windows Built-in Sound (tada.wav)")
    windows_sound = "C:/Windows/Media/tada.wav"
    if os.path.exists(windows_sound):
        print(f"[✓] Found: {windows_sound}")
        print("[*] This will play automatically if no custom jingle is set\n")
    else:
        print(f"[✗] Not found: {windows_sound}\n")
    
    # Test 2: Custom jingle path
    if jingle_path:
        print(f"[Test 2] Custom Jingle: {jingle_path}")
        if os.path.exists(jingle_path):
            print(f"[✓] File found: {jingle_path}")
            print("[*] Testing playback...\n")
            try:
                # Test FFmpeg can read the file
                result = subprocess.run(
                    ['ffmpeg', '-i', jingle_path, '-t', '1', '-f', 'null', '-'],
                    capture_output=True,
                    timeout=10
                )
                print("[✓] Jingle file is valid and playable!\n")
                return True
            except subprocess.TimeoutExpired:
                print("[✗] Playback test timed out\n")
                return False
            except Exception as e:
                print(f"[✗] Error testing jingle: {e}\n")
                return False
        else:
            print(f"[✗] File not found: {jingle_path}\n")
            return False
    else:
        print("[Test 2] Generating Sine Wave Beep (fallback)")
        print("[*] Testing sine wave generation...\n")
        try:
            # Test generating a sine wave
            process = subprocess.Popen(
                ['ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=1000:duration=1',
                 '-f', 'null', '-'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            process.wait()
            print("[✓] Sine wave generation works!\n")
            return True
        except Exception as e:
            print(f"[✗] Error generating sine wave: {e}\n")
            return False

def play_jingle_test(jingle_path=None, duration=2):
    """Actually play the jingle (requires speakers)"""
    print("[*] Playing jingle in 2 seconds...\n")
    
    import time
    time.sleep(2)
    
    try:
        if jingle_path and os.path.exists(jingle_path):
            print(f"[*] Playing: {jingle_path}")
            subprocess.run(
                ['ffmpeg', '-i', jingle_path, '-f', 'null', '-'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10
            )
        else:
            # Play a sine wave
            print("[*] Playing generated beep...")
            subprocess.run(
                ['ffmpeg', '-f', 'lavfi', '-i', f'sine=frequency=1000:duration={duration}',
                 '-f', 'null', '-'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10
            )
        print("\n[✓] Playback complete!\n")
    except Exception as e:
        print(f"\n[✗] Error during playback: {e}\n")

def main():
    print("\nJingle Test Script")
    print("-" * 50)
    
    # Check current directory
    current_dir = os.getcwd()
    print(f"\nCurrent directory: {current_dir}\n")
    
    # List audio files in current directory
    print("[*] Audio files in current directory:")
    audio_extensions = ('.mp3', '.wav', '.ogg', '.flac', '.m4a')
    audio_files = [f for f in os.listdir('.') if f.lower().endswith(audio_extensions)]
    
    if audio_files:
        for i, file in enumerate(audio_files, 1):
            print(f"  {i}. {file}")
    else:
        print("  (none found)")
    print()
    
    # Menu
    print("Options:")
    print("  1. Test Windows built-in sound")
    print("  2. Test custom jingle file")
    print("  3. Test sine wave generation")
    print("  4. Play a jingle test (audio)")
    print("  5. Exit\n")
    
    choice = input("Select option (1-5): ").strip()
    
    if choice == '1':
        result = test_jingle()
        if result:
            input("\nPress Enter to exit...")
    
    elif choice == '2':
        jingle_file = input("\nEnter jingle file path (or filename if in current dir): ").strip()
        if not jingle_file:
            print("[!] No file specified")
            return
        result = test_jingle(jingle_file)
        if result:
            input("\nPress Enter to exit...")
    
    elif choice == '3':
        result = test_jingle()
        if result:
            input("\nPress Enter to exit...")
    
    elif choice == '4':
        print("\n[*] Make sure speakers are turned on!\n")
        jingle_file = input("Enter jingle file path (leave blank for beep): ").strip()
        if jingle_file and not os.path.exists(jingle_file):
            print("[!] File not found")
            return
        
        play = input("Start playback? (y/n): ").strip().lower()
        if play == 'y':
            play_jingle_test(jingle_file if jingle_file else None)
            input("\nPress Enter to exit...")
    
    elif choice == '5':
        print("Exiting...")
        return
    
    else:
        print("[!] Invalid option")

if __name__ == '__main__':
    main()
