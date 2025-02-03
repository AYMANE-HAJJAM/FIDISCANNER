import mysql.connector  # Add this line to fix the error
from flask import Flask, request, session
from twilio.twiml.messaging_response import MessagingResponse
import qrcode
import os
import json
import cloudinary
import cloudinary.uploader
from PIL import Image

# Configure Cloudinary
cloudinary.config(
    cloud_name="dlonah39r",
    api_key="557486886891483",
    api_secret="p5I89-L1C62faI3S6VnyDkBvprM"
)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# MySQL Configuration
DB_CONFIG = {
    "host": "mysql",  # Use the service name
    "user": "root",
    "password": "password",
    "database": "fidiscanner_db"
}


# Ensure necessary directories exist
STATIC_FOLDER = "static"
if not os.path.exists(STATIC_FOLDER):
    os.makedirs(STATIC_FOLDER)

# Path to the base image (update this with your actual image)
BASE_IMAGE_PATH = "image/Scann.jpg"

# Function to get DB connection
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

# Function to load data from MySQL
def load_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, profession, image_url FROM scanner_data")
    data = [{"name": row[0], "profession": row[1], "image_url": row[2]} for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return data

# Function to save data to MySQL
def save_data(name, profession, image_url):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO scanner_data (name, profession, image_url) VALUES (%s, %s, %s)", (name, profession, image_url))
    conn.commit()
    cursor.close()
    conn.close()

# Function to create an image with QR code
def create_image_with_qr(base_image_path, qr_data, output_path):
    try:
        base_image = Image.open(base_image_path).convert("RGBA")

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)

        qr_image = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

        base_width, base_height = base_image.size
        qr_box_size = int(base_width * 0.185)
        qr_image = qr_image.resize((qr_box_size, qr_box_size))

        qr_x = int(base_width * 0.084)
        qr_y = int(base_height * 0.83)

        final_image = base_image.copy()
        final_image.paste(qr_image, (qr_x, qr_y), qr_image)

        final_image.convert("RGB").save(output_path, "JPEG")
        return output_path
    except Exception as e:
        print(f"Error processing image: {str(e)}")
        return None

@app.route("/sms", methods=['POST'])
def reply():
    incoming_msg = request.form.get('Body', '').strip().lower()
    response = MessagingResponse()
    message = response.message()

    # Get the user’s session
    user_state = session.get("user_state", None)

    try:
        # Handle start message at any stage (if user types start, bonjour, or السلام عليكم)
        if incoming_msg in ["start", "bonjour", "السلام عليكم"]:
            # Reset session state
            session.pop("user_state", None)
            session.pop("name", None)
            message.body("Bonjour! Veuillez entrer votre nom complet :")
            session["user_state"] = "waiting_for_name"
            return str(response)

        # If user is in 'waiting_for_name' state
        if user_state == "waiting_for_name":
            # Check if the name is a valid string (only letters and spaces allowed)
            if all(c.isalpha() or c.isspace() for c in incoming_msg):
                name = incoming_msg.strip().capitalize()  # Remove leading/trailing spaces and capitalize
                session["name"] = name  # Store name in session
                session["user_state"] = "waiting_for_profession"
                message.body("Merci! Veuillez entrer votre profession :")
            else:
                # If the name is invalid (contains non-letter and non-space characters)
                message.body("Le nom est invalide. Veuillez entrer un nom correct (seulement des lettres et des espaces).")
                return str(response)  # Stay in 'waiting_for_name' state

            return str(response)

        # If user is in 'waiting_for_profession' state
        elif user_state == "waiting_for_profession":
            # Check if the profession is a valid string (only letters and spaces allowed)
            if all(c.isalpha() or c.isspace() for c in incoming_msg):
                profession = incoming_msg.strip().capitalize()  # Remove leading/trailing spaces and capitalize
                name = session.get("name")  # Retrieve name from session

                # Load existing data from MySQL
                users = load_data()

                # Check if name already exists
                if name not in [user["name"] for user in users]:
                    # Generate QR code image
                    qr_data = f"Nom: {name}, Profession: {profession}"
                    output_image_path = os.path.join(STATIC_FOLDER, f"{name}_final.jpg")

                    final_image_path = create_image_with_qr(BASE_IMAGE_PATH, qr_data, output_image_path)

                    if final_image_path:
                        # Upload to Cloudinary
                        upload_result = cloudinary.uploader.upload(final_image_path)
                        image_url = upload_result['secure_url']

                        # Save data to MySQL
                        save_data(name, profession, image_url)

                        # Respond with the image URL
                        message.body(f"Merci {name}! Voici votre QR Code avec votre profession.")
                        message.media(image_url)
                    else:
                        message.body("Une erreur s'est produite lors de la création de l'image.")
                else:
                    # Respond with the existing QR image
                    existing_user = next(user for user in users if user["name"] == name)
                    message.body(f"Vous avez déjà scanné le QR. Voici votre image : {existing_user['image_url']}")

                # Reset session state
                session.pop("user_state", None)
                session.pop("name", None)
            else:
                # If the profession is invalid (contains non-letter and non-space characters)
                message.body("La profession est invalide. Veuillez entrer une profession correcte (seulement des lettres et des espaces).")
                return str(response)  # Stay in 'waiting_for_profession' state

        else:
            message.body("Entrée non valide. Veuillez entrer un nom valide (seulement des lettres).")

    except Exception as e:
        print(f"Error: {str(e)}")
        message.body(f"Une erreur s'est produite. Veuillez réessayer plus tard. ({str(e)})")

    return str(response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
