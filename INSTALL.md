# PO Scanner — Installation Guide

---

## 1. Install

1. Run **`PO_Scanner_Setup.exe`**
2. Choose an install location (default: `Downloads\PO Scanner`) and click **Next**
3. Optionally check **"Create a desktop shortcut"**
4. Click **Install**, then **Finish**

---

## 2. First Launch

Open **PO Scanner** from the desktop shortcut or Start Menu.  
The app will start and open the camera view.

---

## 3. Settings

Open **PO Scanner Settings** from the Start Menu (or from inside the app).

### Required

**CSV Save Folder**
- Click **Browse** and select the folder where PO CSV files will be saved
- Example: `C:\Users\YourName\Desktop\PO Records`

**Camera**
- Click **↻ Detect** to scan available cameras
- Select the correct camera from the dropdown

Click **💾 Save** when done. Restart PO Scanner to apply changes.

---

### Optional

**PO Blacklist**
- Add words that look like PO numbers but should be ignored (e.g. person names)
- Type the word and click **＋ Add**

**PO Auto-fill Rules**
- When a 7-character PO is scanned, automatically fill in RN and PC based on its first letter
- Click **＋ Add**, choose the PO first letter, enter RN (3 digits), and select PC

---

## 4. Excel Setup

### Prepare the Template

Before generating monthly files, you need one fully set-up `.xlsm` file as a template:
- The file must already have all 30 day sheets formatted with the Sync button
- If you don't have one yet, ask your supervisor for the `Trial Template.xlsm`

### Generate Monthly Files

1. Open **PO Scanner Settings**
2. Go to **Generate Yearly Excel**
3. **Template (.xlsm)** — click Browse and select your `Trial Template.xlsm`
4. **Output folder** — click Browse and select where to save the 12 files
5. **Year** — set the year (e.g. 2026)
6. Click **⚡ Generate 12 Files**

The following files will be created in the output folder:
```
Trial JAN 2026.xlsm
Trial FEB 2026.xlsm
...
Trial DEC 2026.xlsm
```

Each file is a complete copy of the template, ready to use.

---

## 5. Verify Everything Works

- [ ] PO Scanner opens and camera feed is visible
- [ ] Scanning a package shows a PO number
- [ ] CSV file is saved to the correct folder after scanning
- [ ] Settings saves without error
- [ ] Excel files are generated correctly
