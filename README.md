# Co-op Support Application (COSA)


## Team 100 - Sprint 3


## Team Members
- Cynthujan Harichankar - 501233073  
- Suhail Moeen - 501230062  
- Haadia Aamir - 501223714  
- Karan Rangi - 501257634  
- Ammar Kashif - 501242212  
- Samiya Abdirahim - 501102187  


## Project Structure
/COSA_406             -- Project root folder  
│
├── instance/  
│   └── cosa.db        -- SQL database for the application  
│
├── static/   
│   ├── script.js      -- JavaScript file  
│   └── styles.css     -- CSS styles  
│
├── templates/         -- HTML templates used for different routes/views  
│   ├── 2fa.html  
│   ├── add_job.html  
│   ├── admin_dashboard.html  
│   ├── application_review.html  
│   ├── application_status.html  
│   ├── base.html  
│   ├── coordinator_dashboard.html  
│   ├── document_portal.html  
│   ├── edit_user.html  
│   ├── employer_dashboard.html  
│   ├── faq.html  
│   ├── index.html  
│   ├── login.html  
│   ├── manage_user.html  
│   ├── register.html  
│   ├── student_dashboard.html  
│   ├── submit_application.html  
│   ├── upload_report.html  
│   └── view_reminders.html  
│
├── uploads/           -- Folder for uploaded files  
│
├── master.py          -- Main Flask application file  
├── README.md          -- GitHub Markdown version of project description  
└── requirements.txt   -- Python dependencies for running the app  


## Setup Instructions

Before running the code, please ensure you have installed the following:

- Python 3.8 or higher

Once you have Python installed, all you need to do is run the following commands on your terminal:

git clone https://github.com/AmmarK134/COSA_406.git
pip install -r requirements.txt
python master.py


### `requirements.txt` includes the following modules:
- Flask: `pip install Flask`  
- Requests: `pip install requests`  
- SQLAlchemy: `pip install SQLAlchemy`  
- pyotp: `pip install pyotp`  
- qrcode: `pip install qrcode`  