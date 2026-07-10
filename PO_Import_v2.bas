Attribute VB_Name = "PO_Import_v2"
Option Explicit

'===============================================================================
' PO_Import_v2
'
' Architecture:
'   _Data sheet (hidden): all synced records
'       A=Date  B=Carrier  C=Package#  D=Tracking  E=PO  F=Number  G=RN  H=PC
'
'   Day sheets 1-30 (display layer) - v1 layout:
'       A=Package#  B=Date
'       C=USPS Tracking      D=PO  E=Number  F=RN  G=PC
'       H=FedEx Tracking     I=PO  J=Number  K=RN  L=PC
'       M=UPS Tracking       N=PO  O=Number  P=RN  Q=PC
'       R=Amazon Tracking    S=PO  T=Number  U=RN  V=PC
'       W=FedEx EXP Tracking X=PO  Y=Number  Z=RN  AA=PC
'       Row 1: headers  Row 2: Sync button  Rows 3-100: data (pkg# = row-2)
'
' Sync flow:
'   Scan CSV -> find first new record -> use its carrier as target
'   Import up to 12 records of that carrier -> refresh display
'===============================================================================

Private Const DATA_SHEET     As String = "_Data"
Private Const DATA_START_ROW As Long   = 3
Private Const MAX_PER_SYNC   As Long   = 12

Private Function CarrierCol(carrier As String) As Long
    Select Case LCase(Trim(carrier))
        Case "usps":                   CarrierCol = 3
        Case "fedex":                  CarrierCol = 8
        Case "ups":                    CarrierCol = 13
        Case "amazon":                 CarrierCol = 18
        Case "fedex_exp", "fedex exp": CarrierCol = 23
        Case Else:                     CarrierCol = 0
    End Select
End Function

Private Function CarrierLabel(key As String) As String
    Select Case LCase(Trim(key))
        Case "ups":                    CarrierLabel = "UPS"
        Case "fedex":                  CarrierLabel = "FedEx"
        Case "fedex_exp", "fedex exp": CarrierLabel = "FedEx EXP"
        Case "usps":                   CarrierLabel = "USPS"
        Case "amazon":                 CarrierLabel = "Amazon"
        Case Else:                     CarrierLabel = key
    End Select
End Function

' -- Date normalisation --------------------------------------------------------

Private Function NormDate(s As String) As String
    ' Accepts "2026-05-27", "5/27/2026", "2026/5/27", etc.
    On Error Resume Next
    Dim d As Date: d = CDate(Trim(s))
    If Err.Number = 0 Then
        NormDate = Format(d, "yyyy-mm-dd")
    Else
        NormDate = Trim(s)
    End If
    On Error GoTo 0
End Function

' -- Helpers (CSV / YAML) ------------------------------------------------------

Private Function EnMonthName(m As Integer) As String
    Dim n(1 To 12) As String
    n(1) = "January":  n(2) = "February": n(3) = "March"
    n(4) = "April":    n(5) = "May":      n(6) = "June"
    n(7) = "July":     n(8) = "August":   n(9) = "September"
    n(10) = "October": n(11) = "November": n(12) = "December"
    EnMonthName = n(m)
End Function

' Parse month number from workbook name: "Trial MAR 2026.xlsm" -> 3
' Returns 0 if not recognised
Private Function MonthFromWbName(wbName As String) As Integer
    Dim parts() As String: parts = Split(wbName, " ")
    If UBound(parts) < 2 Then MonthFromWbName = 0: Exit Function
    Select Case UCase(parts(1))
        Case "JAN": MonthFromWbName = 1
        Case "FEB": MonthFromWbName = 2
        Case "MAR": MonthFromWbName = 3
        Case "APR": MonthFromWbName = 4
        Case "MAY": MonthFromWbName = 5
        Case "JUN": MonthFromWbName = 6
        Case "JUL": MonthFromWbName = 7
        Case "AUG": MonthFromWbName = 8
        Case "SEP": MonthFromWbName = 9
        Case "OCT": MonthFromWbName = 10
        Case "NOV": MonthFromWbName = 11
        Case "DEC": MonthFromWbName = 12
        Case Else:  MonthFromWbName = 0
    End Select
End Function

Private Function FindCsvFolder(wb As Workbook) As String
    Dim ds As Worksheet: Set ds = GetDataSheet(wb)

    ' 1. Path embedded in _Data!J1 at generate time
    Dim savedPath As String: savedPath = CStr(ds.Cells(1, 10).Value)
    If savedPath <> "" And Dir(savedPath, vbDirectory) <> "" Then
        FindCsvFolder = savedPath
        Exit Function
    End If

    ' 2. Folder picker - last resort
    With Application.FileDialog(msoFileDialogFolderPicker)
        .Title = "Select the CSV folder (where PO_*.csv files are saved)"
        .InitialFileName = Environ("USERPROFILE") & "\Desktop\"
        If .Show = -1 Then
            FindCsvFolder = .SelectedItems(1)
            ds.Cells(1, 10).Value = .SelectedItems(1)
        End If
    End With
End Function

' -- _Data sheet ---------------------------------------------------------------

Private Function GetDataSheet(wb As Workbook) As Worksheet
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = wb.Worksheets(DATA_SHEET)
    On Error GoTo 0
    If ws Is Nothing Then
        Set ws = wb.Worksheets.Add(After:=wb.Worksheets(wb.Worksheets.Count))
        ws.Name = DATA_SHEET
        ws.Range("A1:H1").Value = Array("Date", "Carrier", "Package#", _
                                        "Tracking", "PO", "Number", "RN", "PC")
        ws.Columns("D").NumberFormat = "@"
        ws.Columns("F").NumberFormat = "@"
        ws.Columns("G").NumberFormat = "@"
        ws.Cells(1, 9).Value = Format(Date, "yyyy-mm")  ' workbook month marker
    End If
    ws.Visible = xlSheetHidden
    Set GetDataSheet = ws
End Function

' -- Refresh display from _Data (all carriers, today) -------------------------

Private Sub RefreshView(ws As Worksheet, touchedPkgs As Object)
    ' Only rewrites the rows for packages actually added/updated in this sync
    ' pass (touchedPkgs). Previously this cleared and redrew the whole day's
    ' data area on every sync, which silently wiped out any correction someone
    ' had made by hand directly on this visible sheet since the last sync —
    ' this scopes the redraw down so untouched rows are left alone.
    Dim ds As Worksheet: Set ds = GetDataSheet(ws.Parent)
    Dim todayStr As String: todayStr = Format(Date, "yyyy-mm-dd")

    Dim dsLast As Long: dsLast = ds.Cells(ds.Rows.Count, 1).End(xlUp).Row
    If dsLast < 2 Then Exit Sub

    Dim r As Long
    For r = 2 To dsLast
        If Format(ds.Cells(r, 1).Value, "yyyy-mm-dd") = todayStr Then
            Dim pkgNum As Long
            On Error Resume Next
            pkgNum = CLng(ds.Cells(r, 3).Value)
            If Err.Number <> 0 Then Err.Clear: GoTo NextRow
            On Error GoTo 0

            If Not touchedPkgs.exists(pkgNum) Then GoTo NextRow

            Dim trkCol As Long: trkCol = CarrierCol(CStr(ds.Cells(r, 2).Value))
            If trkCol = 0 Then GoTo NextRow

            Dim excelRow As Long: excelRow = pkgNum + 2

            ws.Range(ws.Cells(excelRow, trkCol), ws.Cells(excelRow, trkCol + 4)).Interior.ColorIndex = xlNone

            ws.Cells(excelRow, 2).Value = CDate(ds.Cells(r, 1).Value)

            ws.Cells(excelRow, trkCol).NumberFormat     = "@"
            ws.Cells(excelRow, trkCol + 2).NumberFormat = "@"
            ws.Cells(excelRow, trkCol + 3).NumberFormat = "@"
            ws.Cells(excelRow, trkCol).Value     = CStr(ds.Cells(r, 4).Value)
            ws.Cells(excelRow, trkCol + 1).Value = ds.Cells(r, 5).Value
            ws.Cells(excelRow, trkCol + 2).Value = ds.Cells(r, 6).Value
            Dim rnRaw As Variant: rnRaw = ds.Cells(r, 7).Value
            Dim rnTxt As String
            If IsNumeric(rnRaw) And Len(Trim(CStr(rnRaw))) > 0 Then
                rnTxt = Format(CLng(rnRaw), "000")
            Else
                rnTxt = CStr(rnRaw)
            End If
            ws.Cells(excelRow, trkCol + 3).Value = rnTxt
            ws.Cells(excelRow, trkCol + 4).Value = ds.Cells(r, 8).Value
        End If
NextRow:
    Next r
End Sub

' -- Format a single day sheet -------------------------------------------------

Private Sub FormatSheet(ws As Worksheet)
    Application.ScreenUpdating = False

    ws.Cells.Clear
    Dim shp As Shape
    For Each shp In ws.Shapes
        shp.Delete
    Next shp

    ' Headers row 1
    Dim hdr As Variant
    hdr = Array( _
        "Package Number", "DATE", _
        "USPS Tracking",      "PO", "NUMBER", "RN", "PC", _
        "FedEx Tracking",     "PO", "NUMBER", "RN", "PC", _
        "UPS Tracking",       "PO", "NUMBER", "RN", "PC", _
        "Amazon Tracking",    "PO", "NUMBER", "RN", "PC", _
        "FedEx EXP Tracking", "PO", "NUMBER", "RN", "PC")
    Dim i As Integer
    For i = 0 To UBound(hdr)
        ws.Cells(1, i + 1).Value = hdr(i)
    Next i

    With ws.Range(ws.Cells(1, 1), ws.Cells(1, 27))
        .Interior.Color      = RGB(255, 255, 0)
        .Font.Bold           = True
        .Font.Size           = 11
        .Font.Name           = "Calibri"
        .HorizontalAlignment = xlCenter
        .VerticalAlignment   = xlCenter
        .RowHeight           = 22
    End With

    ' Column widths
    ws.Columns("A").ColumnWidth  = 14
    ws.Columns("B").ColumnWidth  = 12
    ws.Columns("C").ColumnWidth  = 25
    ws.Columns("D").ColumnWidth  = 10
    ws.Columns("E").ColumnWidth  = 10
    ws.Columns("F").ColumnWidth  = 6
    ws.Columns("G").ColumnWidth  = 6
    ws.Columns("H").ColumnWidth  = 30
    ws.Columns("I").ColumnWidth  = 10
    ws.Columns("J").ColumnWidth  = 10
    ws.Columns("K").ColumnWidth  = 6
    ws.Columns("L").ColumnWidth  = 6
    ws.Columns("M").ColumnWidth  = 28
    ws.Columns("N").ColumnWidth  = 10
    ws.Columns("O").ColumnWidth  = 10
    ws.Columns("P").ColumnWidth  = 6
    ws.Columns("Q").ColumnWidth  = 6
    ws.Columns("R").ColumnWidth  = 22
    ws.Columns("S").ColumnWidth  = 10
    ws.Columns("T").ColumnWidth  = 10
    ws.Columns("U").ColumnWidth  = 6
    ws.Columns("V").ColumnWidth  = 6
    ws.Columns("W").ColumnWidth  = 30
    ws.Columns("X").ColumnWidth  = 10
    ws.Columns("Y").ColumnWidth  = 10
    ws.Columns("Z").ColumnWidth  = 6
    ws.Columns("AA").ColumnWidth = 6

    ' Row 2: Sync button in A2
    ws.Rows(2).RowHeight = 20
    Dim btn As Shape
    Set btn = ws.Shapes.AddShape(msoShapeRoundedRectangle, _
        ws.Range("A2").Left + 1, ws.Range("A2").Top + 1, _
        ws.Range("A2").Width - 2, ws.Range("A2").Height - 2)
    btn.Name     = "btnSync"
    btn.OnAction = "ImportTodayFromCSV"
    With btn.Fill
        .Visible = msoTrue
        .ForeColor.RGB = RGB(204, 30, 30)
        .Solid
    End With
    btn.Line.Visible = msoFalse
    With btn.TextFrame2.TextRange
        .Text = "Sync Records"
        With .Font
            .Name = "Calibri"
            .Size = 9
            .Bold = msoTrue
            .Fill.ForeColor.RGB = RGB(255, 255, 255)
        End With
    End With
    btn.TextFrame.HorizontalAlignment = xlHAlignCenter
    btn.TextFrame.VerticalAlignment   = xlVAlignCenter

    ' Pre-fill package numbers A3:A100
    Dim r As Long
    For r = DATA_START_ROW To 100
        ws.Cells(r, 1).Value              = r - 2
        ws.Cells(r, 1).HorizontalAlignment = xlRight
        ws.Rows(r).RowHeight              = 18
    Next r

    With ws.Range(ws.Cells(DATA_START_ROW, 1), ws.Cells(100, 27))
        .Font.Size         = 10
        .Font.Name         = "Calibri"
        .VerticalAlignment = xlCenter
    End With

    ' Date format on column B
    ws.Columns("B").NumberFormat = "M/D/YYYY"

    ' Force text on Tracking, Number, and RN columns (Number too, so long
    ' numeric-looking values like OCR'd order numbers don't get turned into
    ' scientific notation / lose precision)
    Dim textCols As Variant
    textCols = Array("C", "H", "M", "R", "W", "F", "K", "P", "U", "Z", "E", "J", "O", "T", "Y")
    Dim tc As Variant
    For Each tc In textCols
        ws.Columns(CStr(tc)).NumberFormat = "@"
    Next tc

    ' Borders
    With ws.Range(ws.Cells(1, 1), ws.Cells(100, 27)).Borders
        .LineStyle  = xlContinuous
        .Weight     = xlThin
        .ColorIndex = xlAutomatic
    End With
    With ws.Range(ws.Cells(1, 1), ws.Cells(1, 27)).Borders(xlEdgeBottom)
        .Weight = xlMedium
    End With

    ' Freeze below header
    ws.Activate
    ActiveWindow.FreezePanes = False
    ws.Cells(3, 2).Select
    ActiveWindow.FreezePanes = True
    ActiveWindow.Zoom = 130

    Application.ScreenUpdating = True
End Sub

' -- Public: create all 30 sheets + _Data sheet -------------------------------

Public Sub SetupTemplate_v2()
    Dim wb As Workbook: Set wb = ActiveWorkbook

    Application.ScreenUpdating = False
    Application.DisplayAlerts  = False

    GetDataSheet wb

    On Error Resume Next
    wb.Worksheets("_TEMP_").Delete
    On Error GoTo 0

    Dim tmpWs As Worksheet
    Set tmpWs = wb.Worksheets.Add
    tmpWs.Name = "_TEMP_"

    Dim toDelete() As String
    Dim nDel As Integer: nDel = 0
    Dim ws As Worksheet
    For Each ws In wb.Worksheets
        If ws.Name <> "_TEMP_" And ws.Name <> DATA_SHEET Then
            nDel = nDel + 1
            ReDim Preserve toDelete(1 To nDel)
            toDelete(nDel) = ws.Name
        End If
    Next ws

    Dim i As Integer
    For i = 1 To nDel
        On Error Resume Next
        wb.Worksheets(toDelete(i)).Delete
        On Error GoTo 0
    Next i

    Dim d As Integer
    For d = 1 To 30
        Set ws = wb.Worksheets.Add(After:=wb.Worksheets(wb.Worksheets.Count))
        ws.Name = CStr(d)
        FormatSheet ws
    Next d

    tmpWs.Delete
    wb.Worksheets("1").Activate

    Application.DisplayAlerts  = True
    Application.ScreenUpdating = True

    MsgBox "Done!  30 day sheets (1-30) + _Data backing sheet created." & vbLf & vbLf & _
           "Save as .xlsm to keep macros.", vbInformation, "Setup Complete"
End Sub

' -- Public: import CSV -> _Data -> refresh display -----------------------------

Public Sub ImportTodayFromCSV()
    Dim ws As Worksheet: Set ws = ActiveSheet
    Dim wb As Workbook:  Set wb = ws.Parent

    ' Check user is on the correct day sheet
    Dim todayDay As String: todayDay = CStr(Day(Date))
    If ws.Name <> todayDay Then
        Dim todayWs As Worksheet
        On Error Resume Next
        Set todayWs = wb.Worksheets(todayDay)
        On Error GoTo 0
        If todayWs Is Nothing Then
            MsgBox "Sheet " & todayDay & " not found in this workbook.", vbExclamation, "Wrong Day"
            Exit Sub
        End If
        Dim todayLabel As String
        todayLabel = EnMonthName(Month(Date)) & " " & todayDay
        Dim dayAns As Integer
        dayAns = MsgBox("You are on sheet " & ws.Name & " but today is " & todayLabel & "." & vbLf & vbLf & _
                        "Switch to sheet " & todayDay & " and sync there?", _
                        vbExclamation + vbYesNo, "Wrong Day")
        If dayAns = vbNo Then Exit Sub
        todayWs.Activate
        Set ws = todayWs
    End If

    Dim ds As Worksheet: Set ds = GetDataSheet(wb)

    Dim csvFolder As String: csvFolder = FindCsvFolder(wb)
    If csvFolder = "" Then Exit Sub

    ' Derive month/year from workbook filename: "Trial MAR 2026.xlsm"
    Dim wbYear As Integer, wbMonth As Integer
    wbMonth = MonthFromWbName(wb.Name)
    Dim parts() As String: parts = Split(wb.Name, " ")
    If UBound(parts) >= 2 Then
        Dim yearStr As String: yearStr = Left(parts(2), 4)
        If IsNumeric(yearStr) Then wbYear = CInt(yearStr)
    End If
    If wbMonth = 0 Or wbYear = 0 Then
        wbMonth = Month(Date): wbYear = Year(Date)
    End If

    Dim today    As Date:   today    = Date
    Dim todayStr As String: todayStr = Format(today, "yyyy-mm-dd")
    Dim csvPath  As String
    csvPath = csvFolder & "\" & "PO_" & EnMonthName(wbMonth) & "_" & wbYear & ".csv"

    If Dir(csvPath) = "" Then
        MsgBox "CSV file not found:" & vbLf & csvPath, vbExclamation, "PO Import"
        Exit Sub
    End If

    ' Build dedup maps from _Data (today, key = carrier|package#):
    '   doneComplete = already has both Tracking and PO — normally left alone, but if
    '                  po_scanner re-edits an already-saved package (App-side "edit a
    '                  saved record" flow), the CSV row will differ from what's stored
    '                  here, and this map holds the row number so we can compare and
    '                  update it in place (silently, no highlight — see below).
    '   pendingRow   = still missing Tracking or PO — re-checked every sync and updated in
    '                  place (not re-appended), since po_scanner may complete it later
    '                  without its Package# ever changing
    Dim dsLast As Long: dsLast = ds.Cells(ds.Rows.Count, 1).End(xlUp).Row
    Dim doneComplete As Object: Set doneComplete = CreateObject("Scripting.Dictionary")
    Dim pendingRow   As Object: Set pendingRow   = CreateObject("Scripting.Dictionary")
    Dim r As Long
    For r = 2 To dsLast
        If Format(ds.Cells(r, 1).Value, "yyyy-mm-dd") = todayStr Then
            Dim tk As String: tk = LCase(CStr(ds.Cells(r, 2).Value)) & "|" & CStr(ds.Cells(r, 3).Value)
            Dim rHasTrk As Boolean: rHasTrk = (Trim(CStr(ds.Cells(r, 4).Value)) <> "")
            Dim rHasPO  As Boolean
            rHasPO = (Trim(CStr(ds.Cells(r, 5).Value)) <> "") Or (Trim(CStr(ds.Cells(r, 6).Value)) <> "") _
                     Or (Trim(CStr(ds.Cells(r, 7).Value)) <> "") Or (Trim(CStr(ds.Cells(r, 8).Value)) <> "")
            If rHasTrk And rHasPO Then
                doneComplete(tk) = r
            Else
                pendingRow(tk) = r
            End If
        End If
    Next r

    ' Parse CSV header
    Dim fn As Integer: fn = FreeFile
    On Error GoTo FileError
    Open csvPath For Input As #fn
    On Error GoTo 0

    Dim hdrLine As String
    Line Input #fn, hdrLine
    If Left(hdrLine, 1) = Chr(239) Then hdrLine = Mid(hdrLine, 4)

    Dim hdrs() As String: hdrs = Split(hdrLine, ",")
    Dim iDate As Integer, iCarrier As Integer, iPkg As Integer
    Dim iTrk  As Integer, iPO     As Integer, iNum As Integer
    Dim iRN   As Integer, iPC     As Integer
    Dim j As Integer
    For j = 0 To UBound(hdrs)
        Select Case Trim(hdrs(j))
            Case "Date":     iDate    = j
            Case "Carrier":  iCarrier = j
            Case "Package#": iPkg     = j
            Case "Tracking": iTrk     = j
            Case "PO":       iPO      = j
            Case "Number":   iNum     = j
            Case "RN":       iRN      = j
            Case "PC":       iPC      = j
        End Select
    Next j

    ' First pass: find target carrier from first new record
    Dim targetCarrier As String: targetCarrier = ""
    Dim allLines() As String
    Dim lineCount As Long: lineCount = 0

    Do While Not EOF(fn)
        Dim rawLine As String
        Line Input #fn, rawLine
        If Trim(rawLine) = "" Then GoTo StoreLine

        Dim f() As String: f = Split(rawLine, ",")
        If UBound(f) < iPC Then GoTo StoreLine
        If NormDate(f(iDate)) <> todayStr Then GoTo StoreLine
        If Trim(f(iPkg)) = "" Then GoTo StoreLine

        Dim ck As String: ck = LCase(Trim(f(iCarrier)))
        If CarrierCol(ck) = 0 Then GoTo StoreLine

        If targetCarrier = "" Then
            Dim dedupKey As String: dedupKey = ck & "|" & Trim(f(iPkg))
            Dim isNew As Boolean
            If doneComplete.exists(dedupKey) Or pendingRow.exists(dedupKey) Then
                ' Already imported (complete or still pending) — only counts as "new"
                ' if something actually changed since last sync. This covers both a
                ' pending record getting filled in further, and po_scanner editing an
                ' already-saved/complete record. Otherwise an unchanged package would
                ' keep re-selecting this carrier as the sync target forever, starving
                ' every other carrier whose lines come later in the CSV.
                Dim prevRow As Long
                If doneComplete.exists(dedupKey) Then
                    prevRow = doneComplete(dedupKey)
                Else
                    prevRow = pendingRow(dedupKey)
                End If
                Dim curTrk As String: curTrk = Trim(f(iTrk))
                If Left(curTrk, 1) = "'" Then curTrk = Mid(curTrk, 2)
                isNew = Not (CStr(ds.Cells(prevRow, 4).Value) = curTrk _
                             And CStr(ds.Cells(prevRow, 5).Value) = Trim(f(iPO)) _
                             And CStr(ds.Cells(prevRow, 6).Value) = Trim(f(iNum)) _
                             And CStr(ds.Cells(prevRow, 7).Value) = Trim(f(iRN)) _
                             And CStr(ds.Cells(prevRow, 8).Value) = Trim(f(iPC)))
            Else
                isNew = True
            End If
            If isNew Then targetCarrier = ck
        End If

StoreLine:
        lineCount = lineCount + 1
        ReDim Preserve allLines(1 To lineCount)
        allLines(lineCount) = rawLine
    Loop
    Close #fn

    If targetCarrier = "" Then
        MsgBox "No new records found for today.", vbInformation, "PO Import"
        Exit Sub
    End If

    ' Second pass: import up to MAX_PER_SYNC records for targetCarrier
    Dim added            As Long: added            = 0
    Dim firstHlPkg        As Long: firstHlPkg       = 0  ' first non-resync record this pass, for highlighting
    Dim touchedPkgs As Object: Set touchedPkgs = CreateObject("Scripting.Dictionary")
    Dim idx As Long
    For idx = 1 To lineCount
        If added >= MAX_PER_SYNC Then Exit For
        If Trim(allLines(idx)) = "" Then GoTo NextRow

        Dim fl() As String: fl = Split(allLines(idx), ",")
        If UBound(fl) < iPC Then GoTo NextRow
        If NormDate(fl(iDate)) <> todayStr Then GoTo NextRow
        If LCase(Trim(fl(iCarrier))) <> targetCarrier Then GoTo NextRow
        If Trim(fl(iPkg)) = "" Then GoTo NextRow

        Dim tracking As String: tracking = Trim(fl(iTrk))
        If Left(tracking, 1) = "'" Then tracking = Mid(tracking, 2)
        Dim dk As String:       dk       = targetCarrier & "|" & Trim(fl(iPkg))

        Dim poVal As String:  poVal  = Trim(fl(iPO))
        Dim numVal As String: numVal = Trim(fl(iNum))
        Dim rnVal As String:  rnVal  = Trim(fl(iRN))
        Dim pcVal As String:  pcVal  = Trim(fl(iPC))

        ' Update the existing row in place if this package was already imported
        ' (complete or still pending); otherwise append a new row. A complete
        ' record only reaches here if po_scanner edited an already-saved row —
        ' that's a silent resync (see firstHlPkg below), not a normal new/
        ' completed record, so it shouldn't get the "just synced" highlight.
        Dim writeRow As Long
        Dim isResync As Boolean: isResync = False
        If doneComplete.exists(dk) Then
            writeRow = doneComplete(dk)
            isResync = True
        ElseIf pendingRow.exists(dk) Then
            writeRow = pendingRow(dk)
        Else
            writeRow = ds.Cells(ds.Rows.Count, 1).End(xlUp).Row + 1
        End If

        If doneComplete.exists(dk) Or pendingRow.exists(dk) Then
            ' Already imported and nothing actually changed since last sync — skip
            ' entirely so it doesn't steal the "first changed" highlight/count
            ' from a record that genuinely did change this time.
            If CStr(ds.Cells(writeRow, 4).Value) = tracking _
               And CStr(ds.Cells(writeRow, 5).Value) = poVal _
               And CStr(ds.Cells(writeRow, 6).Value) = numVal _
               And CStr(ds.Cells(writeRow, 7).Value) = rnVal _
               And CStr(ds.Cells(writeRow, 8).Value) = pcVal Then
                GoTo NextRow
            End If
        End If

        ds.Cells(writeRow, 1).Value        = todayStr
        ds.Cells(writeRow, 2).Value        = targetCarrier
        ds.Cells(writeRow, 3).Value        = CLng(Trim(fl(iPkg)))
        ds.Cells(writeRow, 4).NumberFormat = "@"
        ds.Cells(writeRow, 4).Value        = tracking
        ds.Cells(writeRow, 5).Value        = poVal
        ds.Cells(writeRow, 6).NumberFormat = "@"
        ds.Cells(writeRow, 6).Value        = numVal
        ds.Cells(writeRow, 7).NumberFormat = "@"
        ds.Cells(writeRow, 7).Value        = rnVal
        ds.Cells(writeRow, 8).Value        = pcVal

        ' Only mark permanently done once it's actually complete — otherwise leave
        ' it in pendingRow so a later sync re-checks/updates this same row again.
        If tracking <> "" And (poVal <> "" Or numVal <> "" Or rnVal <> "" Or pcVal <> "") Then
            doneComplete(dk) = writeRow
        Else
            pendingRow(dk) = writeRow
        End If
        ' Track the first genuinely new/completed record for highlighting — a
        ' resync earlier in the file must not suppress the highlight for a real
        ' new record later in the same sync pass.
        If Not isResync And firstHlPkg = 0 Then firstHlPkg = CLng(Trim(fl(iPkg)))
        touchedPkgs(CLng(Trim(fl(iPkg)))) = True
        added = added + 1

NextRow:
    Next idx

    If added > 0 Then RefreshView ws, touchedPkgs

    ' Highlight the first genuinely new/completed record this pass (firstHlPkg
    ' already skips resyncs — see above). If every touched record this pass was
    ' a silent resync, firstHlPkg stays 0 and no highlight is applied at all,
    ' leaving whatever highlight was already there untouched.
    If firstHlPkg > 0 Then
        ' Clear whichever cell range was highlighted by the previous sync before
        ' painting the new one. RefreshView used to reset this for free by wiping
        ' the whole day every sync; now that it only touches changed rows, this
        ' "just synced" highlight has to be tracked and cleared explicitly or it
        ' piles up on every row ever highlighted, forever. Persisted in _Data!K1/L1
        ' (row/col) so it survives across sync calls and Excel sessions.
        Dim lastHlRow As Variant: lastHlRow = ds.Cells(1, 11).Value
        Dim lastHlCol As Variant: lastHlCol = ds.Cells(1, 12).Value
        If IsNumeric(lastHlRow) And IsNumeric(lastHlCol) And CLng(lastHlRow) > 0 And CLng(lastHlCol) > 0 Then
            On Error Resume Next
            ws.Range(ws.Cells(CLng(lastHlRow), CLng(lastHlCol)), _
                     ws.Cells(CLng(lastHlRow), CLng(lastHlCol) + 4)).Interior.ColorIndex = xlNone
            On Error GoTo 0
        End If

        Dim hlRow   As Long: hlRow   = firstHlPkg + 2
        Dim hlStart As Long: hlStart = CarrierCol(targetCarrier)
        ws.Range(ws.Cells(hlRow, hlStart), ws.Cells(hlRow, hlStart + 4)).Interior.Color = RGB(255, 255, 153)
        Application.Goto ws.Cells(hlRow, hlStart), True

        ds.Cells(1, 11).Value = hlRow
        ds.Cells(1, 12).Value = hlStart
    End If

    If added = 0 Then
        MsgBox "No new or updated records for " & CarrierLabel(targetCarrier) & " today.", _
               vbInformation, "PO Import"
    Else
        MsgBox added & " record(s) added/updated for " & CarrierLabel(targetCarrier) & ".", _
               vbInformation, "PO Import"
    End If
    Exit Sub

FileError:
    MsgBox "Cannot open CSV file:" & vbLf & csvPath & vbLf & vbLf & _
           "Make sure it is not open in another application.", vbCritical, "PO Import"
End Sub

' -- Public: lock buttons on all 30 day sheets (no password) -------------------

Public Sub LockAllSheetsButtons()
    Dim wb As Workbook: Set wb = ActiveWorkbook
    Dim ws As Worksheet
    Dim shp As Shape
    Dim count As Integer: count = 0

    Application.ScreenUpdating = False

    For Each ws In wb.Worksheets
        If ws.Name = DATA_SHEET Then GoTo NextSheet
        If Not IsNumeric(ws.Name) Then GoTo NextSheet

        ws.Unprotect
        ws.Cells.Locked = False

        For Each shp In ws.Shapes
            shp.Locked = True
        Next shp

        ws.Protect DrawingObjects:=True, Contents:=True, _
                   AllowFormattingCells:=True, AllowFiltering:=True

        count = count + 1
NextSheet:
    Next ws

    Application.ScreenUpdating = True
    MsgBox "Done! Buttons locked on " & count & " sheets.", vbInformation, "Lock Buttons"
End Sub
