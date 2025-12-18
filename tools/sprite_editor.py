"""
Sprite Editor Tool - Convert hex code patterns to color images
16x16 pixel sprite editor with live preview and table input
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageTk
import re

class SpriteEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Sprite Editor - 8x8 / 16x16")
        self.root.geometry("1200x800")
        
        # Sprite size (8x8 or 16x16)
        self.sprite_size = 8  # Default to 8x8
        
        # Default color palette (Index -> Hex Color)
        self.palette = {
            0: "#1E4E1FFF",  # Dunkel, Schatten
            1: "#348C31FF",  # Grundgrün
            2: "#5CAF28FF",  # Helleres Lichtgrün
            3: "#79D021FF",  # Highlight
        }
        
        # Color picker buttons
        self.color_buttons = {}
        
        # Default 8x8 sprite data
        self.default_sprite_8x8 = [
            [1, 1, 2, 1, 1, 2, 1, 1],
            [1, 2, 1, 1, 2, 1, 1, 1],
            [1, 1, 1, 2, 1, 1, 2, 1],
            [1, 1, 2, 1, 1, 1, 1, 2],
            [1, 1, 1, 1, 1, 2, 1, 1],
            [1, 0, 1, 1, 1, 1, 0, 1],
            [1, 1, 0, 1, 1, 0, 1, 1],
            [0, 1, 1, 0, 1, 1, 1, 0]
        ]
        
        # Default 16x16 sprite data
        self.default_sprite_16x16 = [
            [1, 1, 1, 1, 2, 1, 1, 2, 1, 1, 2, 1, 1, 1, 1, 1],
            [1, 1, 2, 1, 1, 1, 2, 1, 1, 2, 1, 1, 1, 2, 1, 1],
            [1, 0, 1, 1, 2, 1, 1, 1, 2, 1, 1, 2, 1, 1, 0, 1],
            [1, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1, 1, 1],
            [1, 1, 2, 1, 1, 0, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1],
            [1, 0, 1, 1, 2, 1, 1, 1, 0, 1, 1, 2, 1, 1, 1, 1],
            [1, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1, 1, 0],
            [1, 1, 2, 1, 1, 1, 0, 1, 1, 2, 1, 1, 1, 1, 2, 1],
            [1, 0, 1, 1, 2, 1, 1, 1, 2, 1, 1, 0, 1, 1, 1, 1],
            [1, 1, 1, 2, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1, 1, 0],
            [0, 1, 1, 1, 1, 0, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1],
            [1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1],
            [0, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0],
            [0, 0, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1],
            [0, 0, 0, 1, 1, 0, 0, 1, 1, 0, 1, 1, 0, 0, 1, 1],
            [0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0]
        ]
        
        self.setup_ui()
        self.load_default_sprite()
        
    def setup_ui(self):
        """Setup the user interface"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # Left side - Text Input
        left_frame = ttk.LabelFrame(main_frame, text="Sprite Data (Paste here)", padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        
        # Size selector
        size_frame = ttk.Frame(left_frame)
        size_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(size_frame, text="Sprite Size:").pack(side=tk.LEFT, padx=(0, 5))
        self.size_var = tk.StringVar(value="8x8")
        size_combo = ttk.Combobox(size_frame, textvariable=self.size_var, values=["8x8", "16x16"], state="readonly", width=10)
        size_combo.pack(side=tk.LEFT)
        size_combo.bind('<<ComboboxSelected>>', self.on_size_change)
        
        # Instructions
        instructions = ttk.Label(
            left_frame, 
            text="Paste your sprite data here.\nSupports: R1:, Row01:, or plain numbers",
            font=("Arial", 9, "italic")
        )
        instructions.pack(pady=(5, 5))
        
        # Text input for sprite data
        from tkinter import scrolledtext
        self.text_input = scrolledtext.ScrolledText(
            left_frame, 
            width=40, 
            height=20, 
            font=("Courier", 10),
            wrap=tk.WORD
        )
        self.text_input.pack(fill=tk.BOTH, expand=True)
        self.text_input.bind('<KeyRelease>', self.on_text_change)
        
        # Buttons below text
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Update Preview", command=self.update_preview).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Clear All", command=self.clear_input).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Detect Colors", command=self.detect_colors).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Save PNG", command=self.save_png).pack(side=tk.LEFT, padx=2)
        
        # Right side - Preview and Palette
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_frame.rowconfigure(1, weight=1)
        
        # Color Palette (dynamic)
        self.palette_frame = ttk.LabelFrame(right_frame, text="Color Palette (Click to change)", padding="10")
        self.palette_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.update_color_palette()
        
        # Preview
        preview_frame = ttk.LabelFrame(right_frame, text="Preview", padding="10")
        preview_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Canvas for preview
        self.preview_canvas = tk.Canvas(preview_frame, width=512, height=512, bg="white")
        self.preview_canvas.pack()
        
        # Status bar
        self.status_label = ttk.Label(main_frame, text="Ready", relief=tk.SUNKEN)
        self.status_label.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
    def update_color_palette(self):
        """Update the color palette display"""
        # Clear existing widgets
        for widget in self.palette_frame.winfo_children():
            widget.destroy()
        
        self.color_buttons.clear()
        
        # Create color picker for each index in palette
        for idx in sorted(self.palette.keys()):
            color = self.palette[idx]
            frame = ttk.Frame(self.palette_frame)
            frame.pack(fill=tk.X, pady=2)
            
            # Color picker button
            color_btn = tk.Button(
                frame, 
                width=4, 
                height=2,
                bg=color[:7],
                command=lambda i=idx: self.pick_color(i)
            )
            color_btn.pack(side=tk.LEFT, padx=(0, 10))
            self.color_buttons[idx] = color_btn
            
            # Label
            label = ttk.Label(frame, text=f"Index {idx}: {color}")
            label.pack(side=tk.LEFT)
    
    def pick_color(self, index):
        """Open color picker for specific index"""
        current_color = self.palette[index][:7]  # Remove alpha
        color = colorchooser.askcolor(
            title=f"Choose color for Index {index}",
            initialcolor=current_color
        )
        
        if color[1]:  # color[1] is the hex string
            # Keep alpha channel
            alpha = self.palette[index][7:9] if len(self.palette[index]) > 7 else "FF"
            self.palette[index] = color[1].upper() + alpha
            
            # Update button color
            self.color_buttons[index].config(bg=color[1])
            
            # Update label
            for widget in self.palette_frame.winfo_children():
                if isinstance(widget, ttk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Label) and f"Index {index}" in child.cget("text"):
                            child.config(text=f"Index {index}: {self.palette[index]}")
            
            # Update preview
            self.update_preview()
            self.status_label.config(text=f"Updated color for index {index}")
    
    def detect_colors(self):
        """Detect all unique indices used in the text and create palette entries"""
        try:
            sprite_data = self.parse_sprite_data()
            indices = set()
            
            for row in sprite_data:
                for value in row:
                    indices.add(value)
            
            # Add missing indices to palette with default colors
            default_colors = [
                "#1E4E1FFF", "#348C31FF", "#5CAF28FF", "#79D021FF",
                "#FF0000FF", "#00FF00FF", "#0000FFFF", "#FFFF00FF",
                "#FF00FFFF", "#00FFFFFF", "#800000FF", "#008000FF",
                "#000080FF", "#808000FF", "#800080FF", "#008080FF"
            ]
            
            for idx in indices:
                if idx not in self.palette:
                    color_idx = idx % len(default_colors)
                    self.palette[idx] = default_colors[color_idx]
            
            # Remove unused indices
            used_indices = set(self.palette.keys()) & indices
            self.palette = {k: v for k, v in self.palette.items() if k in used_indices}
            
            # Update palette display
            self.update_color_palette()
            self.update_preview()
            self.status_label.config(text=f"Detected {len(indices)} unique colors")
        except Exception as e:
            self.status_label.config(text=f"Error detecting colors: {str(e)}")
    
    def on_size_change(self, event=None):
        """Handle sprite size change"""
        size_str = self.size_var.get()
        self.sprite_size = int(size_str.split('x')[0])
        self.load_default_sprite()
        self.status_label.config(text=f"Changed to {size_str} mode")
    
    def load_default_sprite(self):
        """Load default sprite data into text field"""
        # Choose default sprite based on size
        if self.sprite_size == 8:
            default_sprite = self.default_sprite_8x8
        else:
            default_sprite = self.default_sprite_16x16
        
        # Convert 2D array to text format
        text_data = []
        for i, row in enumerate(default_sprite, 1):
            row_str = " ".join(str(x) for x in row)
            text_data.append(f"R{i}: {row_str}")
        
        self.text_input.delete('1.0', tk.END)
        self.text_input.insert('1.0', "\n".join(text_data))
        self.update_preview()
        
    def clear_input(self):
        """Clear text input"""
        self.text_input.delete('1.0', tk.END)
        self.preview_canvas.delete("all")
        self.status_label.config(text="Cleared")
        
    def on_text_change(self, event=None):
        """Auto-update preview on text change (with debounce)"""
        # Cancel previous scheduled update
        if hasattr(self, '_update_job'):
            self.root.after_cancel(self._update_job)
        
        # Schedule new update after 500ms
        self._update_job = self.root.after(500, self.update_preview)
        
    def parse_sprite_data(self):
        """Parse sprite data from text input - supports multiple formats"""
        text = self.text_input.get('1.0', tk.END)
        lines = text.strip().split('\n')
        sprite_data = []
        
        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue
            
            # Remove various row prefixes: R1:, Row01:, Row1:, etc.
            line = re.sub(r'^(R|Row)\d+:\s*', '', line.strip(), flags=re.IGNORECASE)
            
            # Also try to remove just numbers followed by colon (like "1:")
            line = re.sub(r'^\d+:\s*', '', line.strip())
            
            # Split by whitespace and convert to integers
            values = []
            for token in line.split():
                if token.isdigit():
                    values.append(int(token))
            
            # Only add rows with correct number of values for current sprite size
            if len(values) == self.sprite_size:
                sprite_data.append(values)
        
        if len(sprite_data) != self.sprite_size:
            raise ValueError(f"Expected {self.sprite_size} rows with {self.sprite_size} values each, got {len(sprite_data)} valid rows")
        
        return sprite_data
        
    def create_image(self, sprite_data):
        """Create PIL Image from sprite data"""
        # Create image with current sprite size
        size = self.sprite_size
        img = Image.new('RGBA', (size, size))
        pixels = img.load()
        
        for y in range(size):
            for x in range(size):
                index = sprite_data[y][x]
                if index in self.palette:
                    color_hex = self.palette[index]
                    # Convert hex to RGBA
                    r = int(color_hex[1:3], 16)
                    g = int(color_hex[3:5], 16)
                    b = int(color_hex[5:7], 16)
                    a = int(color_hex[7:9], 16) if len(color_hex) > 7 else 255
                    pixels[x, y] = (r, g, b, a)
                else:
                    pixels[x, y] = (255, 0, 255, 255)  # Magenta for invalid index
        
        return img
        
    def update_preview(self):
        """Update the preview canvas"""
        try:
            # Parse sprite data from text
            sprite_data = self.parse_sprite_data()
            
            # Create image
            img = self.create_image(sprite_data)
            
            # Scale up for preview (64x for 8x8 = 512x512, 32x for 16x16 = 512x512)
            scale_factor = 512 // self.sprite_size
            preview_img = img.resize((512, 512), Image.NEAREST)
            
            # Convert to PhotoImage
            self.photo = ImageTk.PhotoImage(preview_img)
            
            # Display on canvas
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(256, 256, image=self.photo)
            
            # Draw grid
            pixel_size = 512 // self.sprite_size
            for i in range(self.sprite_size + 1):
                pos = i * pixel_size
                self.preview_canvas.create_line(pos, 0, pos, 512, fill="#cccccc", width=1)
                self.preview_canvas.create_line(0, pos, 512, pos, fill="#cccccc", width=1)
            
            self.status_label.config(text=f"Preview updated successfully ({self.sprite_size}x{self.sprite_size})")
            
        except ValueError as e:
            self.status_label.config(text=f"Error: {str(e)}")
        except Exception as e:
            self.status_label.config(text=f"Error: {str(e)}")
            
    def save_png(self):
        """Save the sprite as PNG file"""
        try:
            # Parse sprite data from text
            sprite_data = self.parse_sprite_data()
            
            # Create image
            img = self.create_image(sprite_data)
            
            # Ask for save location
            default_name = f"sprite_{self.sprite_size}x{self.sprite_size}.png"
            filename = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
                initialfile=default_name
            )
            
            if filename:
                # Save original (8x8 or 16x16)
                img.save(filename)
                
                # Also save scaled version (512x512)
                scaled_filename = filename.replace(".png", "_scaled.png")
                scaled_img = img.resize((512, 512), Image.NEAREST)
                scaled_img.save(scaled_filename)
                
                self.status_label.config(text=f"Saved: {filename} and {scaled_filename}")
                messagebox.showinfo("Success", 
                    f"Sprite saved successfully!\n\n"
                    f"{self.sprite_size}x{self.sprite_size}: {filename}\n"
                    f"512x512: {scaled_filename}")
            
        except Exception as e:
            self.status_label.config(text=f"Error saving: {str(e)}")
            messagebox.showerror("Error", f"Failed to save sprite:\n{str(e)}")


def main():
    root = tk.Tk()
    app = SpriteEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
