from flask import Flask, render_template, request, redirect, url_for
import os
import xml.etree.ElementTree as ET
import cv2
import csv

app = Flask(__name__)

# Folder paths
IMAGE_FOLDER = os.path.join('static', 'images')
XML_FOLDER = 'xml_files'
CSV_FILE = 'annotations.csv'  # File to store annotation counts
current_image_index = 0
history = []  # To keep track of the image indices for going back
current_user = None

def get_image_files():
    # Returns sorted list of image files
    image_files = sorted([f for f in os.listdir(IMAGE_FOLDER) if f.endswith('.png')])
    return image_files

def draw_bounding_boxes(image_path, xml_file):
    # Read the image
    img = cv2.imread(image_path)
    
    # Parse XML for bounding box information
    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Extract bounding box info and draw it on the image
    for obj in root.findall('object'):
        bndbox = obj.find('bndbox')
        xmin = int(bndbox.find('xmin').text)
        ymin = int(bndbox.find('ymin').text)
        xmax = int(bndbox.find('xmax').text)
        ymax = int(bndbox.find('ymax').text)
        cv2.rectangle(img, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
    
    # Save the new image with bounding boxes in a temporary file
    temp_path = os.path.join(IMAGE_FOLDER, 'temp.png')
    cv2.imwrite(temp_path, img)
    
    return temp_path

def count_annotated_images():
    # Count how many XML files contain at least one <plate_text> tag
    annotated_count = 0
    total_files = 0
    for xml_file in os.listdir(XML_FOLDER):
        if xml_file.endswith('.xml'):
            total_files += 1
            xml_path = os.path.join(XML_FOLDER, xml_file)
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Check if there is at least one <plate_text> in the XML
            if root.findall(".//plate_text"):
                annotated_count += 1
    return annotated_count, total_files

def is_annotated(xml_file):
    # Check if the XML file contains a <plate_text> tag
    tree = ET.parse(xml_file)
    root = tree.getroot()
    return bool(root.findall(".//plate_text"))

def is_flagged(xml_file):
    # Check if the XML file contains a <flagged> tag
    tree = ET.parse(xml_file)
    root = tree.getroot()
    flagged_tag = root.find('flagged')
    return flagged_tag is not None and flagged_tag.text == 'true'

def get_next_unannotated_image():
    global current_image_index
    image_files = get_image_files()
    
    # Loop to find the next unannotated image
    while current_image_index < len(image_files):
        image_file = image_files[current_image_index]
        xml_file = os.path.join(XML_FOLDER, image_file.replace('.png', '.xml'))
        
        if not is_annotated(xml_file):  # If not annotated, return the file
            return image_file
        current_image_index += 1  # Move to next image if already annotated
    
    return None  # Return None if all images are annotated

def update_annotation_count(user_name):
    # If the CSV file does not exist, create it and write headers
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['user_name', 'annotations_count'])

    # Read current data
    users = {}
    with open(CSV_FILE, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            users[row['user_name']] = int(row['annotations_count'])
    
    # Update the count for the user
    if user_name in users:
        users[user_name] += 1
    else:
        users[user_name] = 1
    
    # Write updated data back to the CSV
    with open(CSV_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['user_name', 'annotations_count'])
        for name, count in users.items():
            writer.writerow([name, count])

def get_annotation_counts():
    # Read the CSV and return a list of user annotation counts
    if not os.path.exists(CSV_FILE):
        return []
    
    annotation_counts = []
    with open(CSV_FILE, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            annotation_counts.append(row)
    return annotation_counts

@app.route('/', methods=['GET', 'POST'])
def index():
    global current_user
    if request.method == 'POST':
        current_user = request.form['user_name']
        return redirect(url_for('annotate'))
    return render_template('index.html')

@app.route('/annotate', methods=['GET', 'POST'])
def annotate():
    global current_image_index, history

    if request.method == 'POST':
        if 'submit' in request.form or 'not_sure' in request.form:
            # Store the current index in history before moving to the next image
            history.append(current_image_index)
            
            plate_text = request.form.get('license_plate', '')
            xml_file = os.path.join(XML_FOLDER, get_image_files()[current_image_index].replace('.png', '.xml'))
            add_plate_text_to_xml(xml_file, plate_text)
            update_annotation_count(current_user)
            
            # Move to the next unannotated image
            current_image_index = find_next_unannotated_image_index(current_image_index + 1)
            
            return redirect(url_for('annotate'))
        elif 'back' in request.form:
            if history:
                current_image_index = history.pop()
            return redirect(url_for('annotate'))
        elif 'flag' in request.form:
            # Store the current index in history before moving to the next image
            history.append(current_image_index)
            
            xml_file = os.path.join(XML_FOLDER, get_image_files()[current_image_index].replace('.png', '.xml'))
            flag_image_as_bad(xml_file)
            
            # Move to the next unannotated image
            current_image_index = find_next_unannotated_image_index(current_image_index + 1)
            
            return redirect(url_for('annotate'))

    image_file = get_image_files()[current_image_index] if current_image_index < len(get_image_files()) else None
    if image_file is None:  # All images are annotated
        return "All images annotated!"
    
    xml_file = os.path.join(XML_FOLDER, image_file.replace('.png', '.xml'))
    image_path = os.path.join(IMAGE_FOLDER, image_file)
    temp_image_path = draw_bounding_boxes(image_path, xml_file)  # Bounding boxes always ON by default

    annotated_count, total_files = count_annotated_images()

    # Get annotation counts for all users
    annotation_counts = get_annotation_counts()

    return render_template('annotation.html', image_file=temp_image_path, image_name=image_file,
                           annotated_count=annotated_count, total_files=total_files,
                           annotation_counts=annotation_counts)

def find_next_unannotated_image_index(start_index):
    image_files = get_image_files()
    for i in range(start_index, len(image_files)):
        xml_file = os.path.join(XML_FOLDER, image_files[i].replace('.png', '.xml'))
        if not is_annotated(xml_file) and not is_flagged(xml_file):
            return i
    return start_index  # If no unannotated image found, stay on the current one


def add_plate_text_to_xml(xml_file, plate_text):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    obj = root.find('object')
    if obj is not None:
        plate_text_tag = ET.SubElement(obj, 'plate_text')
        plate_text_tag.text = plate_text
        tree.write(xml_file)

def flag_image_as_bad(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Add <flagged> tag if not already present
    flagged_tag = root.find('flagged')
    if flagged_tag is None:
        flagged_tag = ET.SubElement(root, 'flagged')

    # Set <flagged> tag to true
    flagged_tag.text = 'true'
    
    # Write the changes back to the XML file
    tree.write(xml_file)

if __name__ == '__main__':
    app.run(debug=True)
