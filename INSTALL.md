# PO Scanner — Installation Guide

---

## Part 1 — Get the Files

1. Open **File Explorer**
2. Click the address bar at the top
3. Type `\\172.17.32.40\Maint\Wenbin\Chiout\Warehouse` and press **Enter**
4. Find the file **`PO_Scanner_Setup.exe`**
5. Right-click it and select **Copy**
6. Go to your local Desktop and paste it there
7. Go back to the network folder
8. Find the file **`Trial Template.xlsm`**
9. Right-click it and select **Copy**
10. Go to your local Desktop and paste it there
11. Wait for both files to finish copying before continuing

---

## Part 2 — Run the Installer

1. On your Desktop, find **`PO_Scanner_Setup.exe`**
2. Right-click on it
3. Select **Open** (do not double-click — Windows may block it)
4. If a blue warning screen appears saying **"Windows protected your PC"**:
   - Click **More info**
   - Click **Run anyway**
5. The installer window opens
6. On the **"Select Destination Location"** screen, the default path is `C:\PO Scanner`
7. Leave the path as default (do not change it)
8. Click **Next**
9. If you want a desktop shortcut, check **"Create a desktop shortcut"**
10. Click **Next**
11. Click **Install**
12. Wait for the progress bar to complete
13. On the final screen, make sure **"Launch PO Scanner"** is **NOT checked**
14. Click **Finish**

---

## Part 3 — Open Settings

1. Open **File Explorer**
2. Navigate to `C:\PO Scanner`
3. Find the file **`settings.exe`**
4. Right-click on it
5. Select **Open**
6. The **PO Scanner Settings** window opens

---

## Part 4 — Set the CSV Save Folder

1. In the Settings window, find the **"CSV save folder"** field
2. Click the **Browse** button next to it
3. In the folder browser, navigate to `\\172.17.32.40\Maint\Wenbin\Chiout\Warehouse\csv`
4. Click **Select Folder**
5. The path appears in the CSV save folder field

---

## Part 5 — Set Up the Camera

1. In the Settings window, find the **"Camera"** section
2. Click the **↻ Detect** button
3. Wait a moment for the camera list to load
4. Click the dropdown that appears
5. Select **Rear Camera** (or the camera labelled as the scanner)

---

## Part 6 — Save Settings

1. Click the **💾 Save** button at the bottom of the Settings window
2. A dialog box appears confirming the settings were saved
3. Click **OK**
4. Close the Settings window

---

## Part 7 — Copy the Template File

1. Open **File Explorer**
2. Navigate to `C:\PO Scanner\Template`
3. Go back to your Desktop
4. Find **`Trial Template.xlsm`** (copied in Part 1)
5. Right-click it and select **Copy**
6. Go back to `C:\PO Scanner\Template`
7. Right-click inside the folder and select **Paste**
8. Wait for the file to finish copying

---

## Part 8 — Generate Yearly Excel Files

1. Open **`settings.exe`** again (same steps as Part 3)
2. Scroll down to the **"Generate Yearly Excel"** section
3. Next to **"Template (.xlsm)"**, click **Browse**
4. Navigate to `C:\PO Scanner\Template`
5. Select **`Trial Template.xlsm`**
6. Click **Open**
7. Next to **"Output folder"**, click **Browse**
8. Navigate to `C:\PO Scanner\Template`
9. Click **Select Folder**
10. Set the **Year** field to the current year (e.g. 2026)
11. Click **⚡ Generate 12 Files**
12. A confirmation dialog appears
13. Click **OK**
14. Open `C:\PO Scanner\Template` in File Explorer
15. Verify that 12 files were created (Trial JAN 2026.xlsm through Trial DEC 2026.xlsm)

---

## Part 9 — Launch PO Scanner

1. Double-click the **PO Scanner** shortcut on the Desktop
   — OR —
   Open `C:\PO Scanner` and double-click **`po_scanner.exe`**
2. The camera view opens
3. Point the camera at a package label
4. The PO number is detected and shown on screen

---

## Checklist

- [ ] PO Scanner opens and the camera feed is visible
- [ ] Scanning a package shows a PO number on screen
- [ ] CSV file is saved to the network folder after scanning
- [ ] 12 Excel files are present in `C:\PO Scanner\Template`
