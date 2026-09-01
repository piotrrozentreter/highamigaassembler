# 🛠️ Project Specification: GUI Builder for Amiga DOS (68000)
**(V2.0 - HAS Language Integration)**

## I. Context and Agent Role Definition
**Project Goal:** Development of a WYSIWYG Graphical User Interface Designer Tool for the Amiga 68k architecture.
**AI Agent's Role:** You are to act as an experienced Systems Software Engineer specializing in meta-generative tools. Your task is to design and partially implement the GUI Builder using Python. **Crucially, this program will NOT be a standalone application.** It serves only as an editor that generates structured input data (metadata) for our 68000 assembler/compiler pipeline.
**Primary Objective:** The tool must allow users to visually construct the layout of a window and add controls. Instead of generating high-level source code, it must export **highly structured pseudo-code metadata in the proprietary HAS language format.**

## II. System Architecture (Output Protocol)
The output is not raw data; it is organized pseudo-code that simulates the structure required by the Amiga DOS API and our custom compiler (`HAS`).

### 2.1 Output File Structure (HAS Metadata Format)
The generated file must be logically segmented to ensure compatibility with the assembly loader:

```assembly
; --- METADATA HEADER ---
DEFINE_WINDOW Caption="Window Title" WIDTH=800 HEIGHT=600 ; HAS/Amiga API call simulation
BEGIN_GUI_LAYOUT
    ; ... (Control definitions follow)
END_GUI_LAYOUT

; --- EVENT HANDLER DEFINITIONS ---
DEFINE_EVENT_HANDLERS START_MODULE
    HANDLE_ACTION(ID: 1, ACTION: BUTTON_CLICK): CALL_FUNCTION(amiga_button_action_1); ; Event mapping for assembly
    HANDLE_ACTION(ID: 2, ACTION: EDITBOX_CHANGE): PROCESS_INPUT(memory_offset=0x...);

; --- CONSTANTS/LAYOUT DATA (For Assembler Consumption) ---
SECTION DATA CONSTANTS
    WINDOW_CAPTION EQU "Window Title"
    CONTROL_TYPE_BUTTON   EQU 1
    ...
```

### 2.2 Window Handling Functions
The core function for window display must be defined in the metadata:
*   **Function:** `DEFINE_WINDOW`
*   **Parameters:** Caption (String), Width (Integer), Height (Integer).
*   **Implementation Requirement:** This macro/function simulates the initial call to the Amiga DOS API required to create and manage the main window resource.

## III. Functional Requirements (Minimum Viable Product - MVP)

### 3.1 User Interface (Python GUI Builder)
1.  **WYSIWYG Preview:** Must provide an interactive preview mimicking a retro Amiga OS look and feel, showing the real-time layout of controls within the defined window boundaries.
2.  **Control Panel/Toolbox:** A panel allowing users to add elements via click or Drag & Drop: Button, EditBox, Label.
3.  **Global Settings:** Input fields for Window Parameters: Caption (String), Width (Integer), Height (Integer).

### 3.2 Control Logic and Pseudo-Code Generation
The Python logic must track geometry (X, Y, W, H) AND generate the corresponding pseudo-code based on the element type. The metadata generation process is paramount.

| Element | Attributes to Capture | Generated HAS Pseudo-Code Example | Amiga DOS Purpose |
| :--- | :--- | :--- | :--- |
| **Window** | Caption, W, H | `DEFINE_WINDOW Caption="{TITLE}" WIDTH={W} HEIGHT={H}` | Resource Initialization and Window Management. |
| **Button** | Caption, X, Y, W, H | `{CALL_HAS_CMD: ADD_CONTROL(TYPE=BUTTON, ID={ID}, X={X}, Y={Y}, CAPT="{CAP}")}` | Defines the widget and links it to a unique, processable Event ID. |
| **EditBox** | InitialText, X, Y, W, H | `{CALL_HAS_CMD: ADD_CONTROL(TYPE=EDITBOX, ID={ID}, X={X}, Y={Y}, ITEXT="{INIT}")}` | Defines the widget and provides hooks for input change events. |
| **Label** | Text, X, Y, W, H | `{CALL_HAS_CMD: ADD_CONTROL(TYPE=LABEL, ID={ID}, X={X}, Y={Y}, TEXT="{TXT}")}` | Static decoration; minimal code generation required. |

## IV. Implementation Plan and Deliverables (Phases)

The implementation must be structured into three distinct phases to ensure progressive development of the metadata generation logic.

### Phase 1: Data Architecture & Basic GUI
*   **Deliverable:** A Python `MetadataManager` class capable of holding a list of control objects.
*   **Implementation Focus:** Implementing basic window setup (`DEFINE_WINDOW`) and adding static elements (Labels). The generated output must be structurally sound but functionally simple.

### Phase 2: Interactivity & Event Handling
*   **Deliverable:** Integration of Button and EditBox controls.
*   **Core Logic:** Introduce a mandatory `ActionID` counter that increments every time an interactive element is added. This ID must be linked to the generated HAS code's event handler section (`HANDLE_ACTION`). The metadata must simulate the logic for click/change events.

### Phase 3: Finalization and Architectural Documentation
*   **Deliverable:** Fully functional GUI Builder generating comprehensive pseudo-code in `.hasmeta` format.
*   **Mandatory Output:** A detailed **Technical Commentary** explaining how the generated data structure (`X, Y, W, H`, `Type`, `ID`) maps directly into assembler constants and which specific Amiga DOS API calls must be executed by the resulting compiled HAS program.

### 🔑 Key Deliverable Summary:
1.  **Python Code:** The GUI Builder logic.
2.  **Output File (`.hasmeta`):** A file containing syntactically correct pseudo-code in the HAS language structure, ready for our compiler/assembler pipeline.
3.  **Document:** Prepare a document for the amigados agent about what functions must be create to display controls. Prepare a startup HAS code for displaying the window/dialog with an empty functions/handler for all events.
