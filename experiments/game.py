import pygame
import cv2
import sounddevice as sd
import numpy as np
import webbrowser
from io import StringIO
import contextlib
import sys

# Initialize Pygame
pygame.init()

# Set up some constants
WIDTH, HEIGHT = 800, 600
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
GRAY = (128, 128, 128)

# Set up the display
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Multi-Tool Application")

# Set up the font
font = pygame.font.SysFont("Arial", 20)
small_font = pygame.font.SysFont("Arial", 16)

# Set up the clock
clock = pygame.time.Clock()

class Button:
    def __init__(self, text, x, y, width, height, color, hover_color):
        self.text = text
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = color
        self.hover_color = hover_color

    def draw(self, screen):
        mouse = pygame.mouse.get_pos()
        if self.x <= mouse[0] <= self.x + self.width and self.y <= mouse[1] <= self.y + self.height:
            pygame.draw.rect(screen, self.hover_color, (self.x, self.y, self.width, self.height), border_radius=10)
        else:
            pygame.draw.rect(screen, self.color, (self.x, self.y, self.width, self.height), border_radius=10)

        text_surface = font.render(self.text, True, WHITE)
        screen.blit(text_surface, (self.x + (self.width - text_surface.get_width()) // 2, 
                                 self.y + (self.height - text_surface.get_height()) // 2))

    def is_clicked(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.x <= event.pos[0] <= self.x + self.width and self.y <= event.pos[1] <= self.y + self.height:
                return True
        return False

class TextInput:
    def __init__(self, x, y, width, height, placeholder=""):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text = ""
        self.placeholder = placeholder
        self.active = True

    def draw(self, screen):
        color = WHITE if self.active else GRAY
        pygame.draw.rect(screen, color, (self.x, self.y, self.width, self.height), 2, border_radius=5)
        
        display_text = self.text if self.text else self.placeholder
        text_color = WHITE if self.text else GRAY
        text_surface = font.render(display_text, True, text_color)
        screen.blit(text_surface, (self.x + 5, self.y + 5))

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_ESCAPE:
                return "escape"
            elif event.key == pygame.K_RETURN:
                return "enter"
            else:
                if len(self.text) < 50:  # Limit text length
                    self.text += event.unicode
        return None

def show_instructions(screen, instructions):
    """Display instructions on screen"""
    y_offset = 50
    for line in instructions:
        text_surface = small_font.render(line, True, WHITE)
        screen.blit(text_surface, (50, y_offset))
        y_offset += 25

def take_screenshot():
    instructions = [
        "Screenshot Tool",
        "Type one of the following commands:",
        "- 'full' for full screen",
        "- 'window' for current window", 
        "- 'area' for selected area",
        "Press Enter to execute, Escape to go back"
    ]
    
    text_input = TextInput(50, 200, 300, 30, "Enter command...")
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            result = text_input.handle_event(event)
            if result == "escape":
                return
            elif result == "enter":
                screenshot_type = text_input.text.lower().strip()
                try:
                    import pyautogui
                    if screenshot_type == "full":
                        image = pyautogui.screenshot()
                        image.save("screenshot_full.png")
                        print("Full screenshot saved as screenshot_full.png")
                    elif screenshot_type == "window":
                        # Take a centered window screenshot
                        image = pyautogui.screenshot(region=(100, 100, 600, 400))
                        image.save("screenshot_window.png")
                        print("Window screenshot saved as screenshot_window.png")
                    elif screenshot_type == "area":
                        image = pyautogui.screenshot(region=(200, 200, 400, 300))
                        image.save("screenshot_area.png")
                        print("Area screenshot saved as screenshot_area.png")
                    else:
                        print("Invalid command. Use 'full', 'window', or 'area'")
                        continue
                except ImportError:
                    print("pyautogui not installed. Install with: pip install pyautogui")
                except Exception as e:
                    print(f"Error taking screenshot: {e}")
                return

        screen.fill(BLACK)
        show_instructions(screen, instructions)
        text_input.draw(screen)
        pygame.display.flip()
        clock.tick(60)

def open_camera():
    instructions = [
        "Camera Tool",
        "Type one of the following commands:",
        "- 'open' to open webcam view",
        "- 'photo' to take a photo",
        "- 'video' to record video (press 'q' to stop)",
        "Press Enter to execute, Escape to go back"
    ]
    
    text_input = TextInput(50, 200, 300, 30, "Enter command...")
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            result = text_input.handle_event(event)
            if result == "escape":
                return
            elif result == "enter":
                camera_mode = text_input.text.lower().strip()
                try:
                    if camera_mode == "open":
                        cap = cv2.VideoCapture(0)
                        if not cap.isOpened():
                            print("Cannot open camera")
                            continue
                        while True:
                            ret, frame = cap.read()
                            if not ret:
                                break
                            cv2.imshow('Camera - Press Q to quit', frame)
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break
                        cap.release()
                        cv2.destroyAllWindows()
                    elif camera_mode == "photo":
                        cap = cv2.VideoCapture(0)
                        if not cap.isOpened():
                            print("Cannot open camera")
                            continue
                        ret, frame = cap.read()
                        if ret:
                            cv2.imwrite("photo.png", frame)
                            print("Photo saved as photo.png")
                        cap.release()
                    elif camera_mode == "video":
                        cap = cv2.VideoCapture(0)
                        if not cap.isOpened():
                            print("Cannot open camera")
                            continue
                        fourcc = cv2.VideoWriter_fourcc(*'XVID')
                        out = cv2.VideoWriter('video.avi', fourcc, 20.0, (640, 480))
                        print("Recording... Press 'q' to stop")
                        while True:
                            ret, frame = cap.read()
                            if not ret:
                                break
                            out.write(frame)
                            cv2.imshow('Recording - Press Q to stop', frame)
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break
                        cap.release()
                        out.release()
                        cv2.destroyAllWindows()
                        print("Video saved as video.avi")
                    else:
                        print("Invalid command. Use 'open', 'photo', or 'video'")
                        continue
                except Exception as e:
                    print(f"Camera error: {e}")
                return

        screen.fill(BLACK)
        show_instructions(screen, instructions)
        text_input.draw(screen)
        pygame.display.flip()
        clock.tick(60)

def record_microphone():
    instructions = [
        "Microphone Recorder",
        "Enter the duration in seconds (e.g., 5)",
        "Press Enter to start recording, Escape to go back"
    ]
    
    text_input = TextInput(50, 150, 200, 30, "Duration in seconds...")
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            result = text_input.handle_event(event)
            if result == "escape":
                return
            elif result == "enter":
                try:
                    duration = float(text_input.text)
                    if duration <= 0 or duration > 60:
                        print("Please enter a duration between 1 and 60 seconds")
                        continue
                    
                    print(f"Recording for {duration} seconds...")
                    fs = 44100
                    myrecording = sd.rec(int(duration * fs), samplerate=fs, channels=2)
                    sd.wait()
                    
                    try:
                        import soundfile as sf
                        sf.write('audio.wav', myrecording, fs)
                        print("Audio saved as audio.wav")
                    except ImportError:
                        print("soundfile not installed. Install with: pip install soundfile")
                except ValueError:
                    print("Please enter a valid number")
                    continue
                except Exception as e:
                    print(f"Recording error: {e}")
                return

        screen.fill(BLACK)
        show_instructions(screen, instructions)
        text_input.draw(screen)
        pygame.display.flip()
        clock.tick(60)

def open_browser():
    instructions = [
        "Browser Tool",
        "Enter a URL to open in your default browser",
        "Example: https://www.google.com",
        "Press Enter to open, Escape to go back"
    ]
    
    text_input = TextInput(50, 150, 400, 30, "Enter URL...")
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            result = text_input.handle_event(event)
            if result == "escape":
                return
            elif result == "enter":
                url = text_input.text.strip()
                if not url:
                    continue
                
                # Add protocol if missing
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                
                try:
                    webbrowser.open(url)
                    print(f"Opened: {url}")
                except Exception as e:
                    print(f"Error opening browser: {e}")
                return

        screen.fill(BLACK)
        show_instructions(screen, instructions)
        text_input.draw(screen)
        pygame.display.flip()
        clock.tick(60)

def python_console():
    instructions = [
        "Python Console",
        "Enter Python code and press Enter to execute",
        "Press Escape to go back"
    ]
    
    text_input = TextInput(50, 150, 600, 30, "Enter Python code...")
    output_lines = []
    scroll_offset = 0
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            result = text_input.handle_event(event)
            if result == "escape":
                return
            elif result == "enter":
                code = text_input.text.strip()
                if not code:
                    continue
                
                output_lines.append(f">>> {code}")
                
                try:
                    # Capture stdout
                    f = StringIO()
                    with contextlib.redirect_stdout(f):
                        exec(code)
                    output = f.getvalue()
                    if output:
                        output_lines.extend(output.strip().split('\n'))
                    else:
                        output_lines.append("(no output)")
                except Exception as e:
                    output_lines.append(f"Error: {str(e)}")
                
                # Limit output history
                if len(output_lines) > 20:
                    output_lines = output_lines[-20:]
                
                text_input.text = ""

        screen.fill(BLACK)
        show_instructions(screen, instructions)
        text_input.draw(screen)
        
        # Display output
        y_offset = 200
        for line in output_lines[-10:]:  # Show last 10 lines
            if y_offset < HEIGHT - 50:
                output_surface = small_font.render(line[:80], True, GREEN)  # Limit line length
                screen.blit(output_surface, (50, y_offset))
                y_offset += 20
        
        pygame.display.flip()
        clock.tick(60)

def main():
    buttons = [
        Button("Take Screenshot", 100, 100, 200, 50, BLUE, (0, 150, 255)),
        Button("Open Camera", 350, 100, 200, 50, GREEN, (0, 220, 0)),
        Button("Record Microphone", 100, 200, 200, 50, RED, (255, 100, 0)),
        Button("Open Browser", 350, 200, 200, 50, (255, 165, 0), (255, 215, 0)),
        Button("Python Console", 225, 300, 200, 50, (75, 0, 130), (100, 0, 150)),
    ]

    running = True
    while running:
        screen.fill(BLACK)
        
        # Title
        title_surface = font.render("Multi-Tool Application", True, WHITE)
        screen.blit(title_surface, (WIDTH//2 - title_surface.get_width()//2, 30))

        for button in buttons:
            button.draw(screen)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            for button in buttons:
                if button.is_clicked(event):
                    if button.text == "Take Screenshot":
                        take_screenshot()
                    elif button.text == "Open Camera":
                        open_camera()
                    elif button.text == "Record Microphone":
                        record_microphone()
                    elif button.text == "Open Browser":
                        open_browser()
                    elif button.text == "Python Console":
                        python_console()

        pygame.display.flip()
        clock.tick(60)


    pygame.quit()
if __name__ == "__main__":
 main()