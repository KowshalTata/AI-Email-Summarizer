from simplegmail import Gmail
from simplegmail.query import construct_query
from bs4 import BeautifulSoup
import re 
import supabase
from supabase import *
from datetime import datetime
import requests
import requests.exceptions
from openai import OpenAI
from google.cloud import texttospeech
import os
import traceback
from dotenv import load_dotenv
from wordcloud import WordCloud, STOPWORDS
import matplotlib.pyplot as plt
import numpy as np

# Load variables from .env file
load_dotenv()
import os

# Supabase
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase_client = supabase.create_client(supabase_url, supabase_key)
supabase_table_name = os.environ.get("SUPABASE_TABLE")

# OpenAI
openai_api_key = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key)
gpt_model = "gpt-3.5-turbo-0125"
#gpt_model = "gpt-4"
# personality_env = """Compose a script analyzing newsletters focused on [User Custom Topic]. Craft a compelling and well-organized narrative, akin to a professional newsletters analyst. Ensure the content is suitable for narration via a Text-to-Speech (TTS) system API. The aim is to present informative material in a conversational style, exclusively drawing from the specified topic and avoiding external sources.
# Please adhere to the following guidelines:
# Exclude stage directions like [Opening Music], [Transition Music], [Host], as these will be manually added based on TTS audio file requirements.
# Maintain brevity and informativeness by limiting the response to key points, encompassing all highlights related to the topic. This approach ensures that listeners of the voice clip remain engaged and attentive without feeling overwhelmed."""

personality_env = """Generate a news letters analysis script on the topic of [User Custom Topic]. Provide an engaging and well-structured narrative, similar to a professional news letters analyzer. Ensure the response is suitable for narration through a Text-to-Speech (TTS) system API. The goal is to deliver informative content with a conversational tone, drawing exclusively from the provided topic and without incorporating outside knowledge.
Please note:
- Do not include any stage directions such as [Opening Music], [Transition Music], [Host]. Those will be manually added as per the requirements into the TTS generated audio file.
- Keep it short and informative by limiting the response to a few points, covering all the highlights from the topic, so that users listening to this as a voice clip will stay attentive to details and will not be irritated."""

background_color="white"

# Google
google_application_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = google_application_credentials



###### Stage Zero - Extract the filtered message from my gmail inbox
def get_filtered_messages():
    gmail = Gmail()

    #Define query parameters
    query_params = {
        "newer_than": (1, "day"),
    }

    # Get filtered messages
    messages = gmail.get_messages(query=construct_query(query_params))
    return messages

def extract_name_from_sender(sender_str):
    # Dictionary to map sender names to replacements
    sender_replacements = {
        #"Mike Allen": "Axios AM PM",
        # Add more mappings here as needed
    }

    # Extract only the name from the "From" field
    match = re.match(r'(.+?)\s*<', sender_str)
    if match:
        name = match.group(1).strip()
        # Check if the name needs to be replaced
        if name in sender_replacements:
            name = sender_replacements[name]
        return name
    else:
        return sender_str.strip()

    
#Allowed sender names
allowed_senders = ['Techpresso', 'The Neuron', 'The Average Joe', 'Morning Brew', 'Dan Primack', 'CFO Brew', 'Daniel Murray', '10almonds', 'Game Rant', 'Axios AM PM',"Axios Vitals", "DTC Daily" ]
# allowed_senders = ['DTC Daily'] # Use this when using the gpt 4 to avoid repetative pattrens error of gpt 3.5
def get_sender_category(sender_name):
    # Define a mapping of sender names to categories
    sender_categories = {
        "Morning Brew": "World",
        "Dan Primack": "Finance",
        "Axios AM PM": "World",
        "The Average Joe": "Finance",
        "CFO Brew": "Finance",
        "The Neuron": "AI & Tech",
        "Techpresso": "AI & Tech",
        "TLDR": "AI & Tech",
        "TLDR AI": "AI & Tech",
        "DTC Daily": "Marketing",
        "Daniel Murray": "Marketing",
        "TLDR Marketing": "Marketing",
        "10almonds": "Health",
        "Axios Vitals": "Health",
        "Game Rant": "Gaming"      
        # Add more sender-category mappings as needed
    }
    
    # Get the category for the sender or use a default category
    return sender_categories.get(sender_name, "Other")

# Get filtered messages
messages = get_filtered_messages()

# Filter messages based on sender name  
Messages = []
for message in messages:
    sender_name = extract_name_from_sender(message.sender)
    # Check if the sender's name matches the allowed names or starts with "TLDR"
    if sender_name in allowed_senders or sender_name.startswith('TLDR'):
        # Add the message to the filtered list
        Messages.append(message)


# # senders confirmation
# senders = []
# for message in Messages:
#     senders.append(extract_name_from_sender(message.sender))
# print(senders)
        
# Print sender names along with subjects
for message in Messages:
    sender_name = extract_name_from_sender(message.sender)
    subject = message.subject
    print("                                                                                                      ")
    print(f"{sender_name}: {subject}")
    print("                                                                                                      ")

confirmation = input("Are these all the senders you are expecting today? (yes/no): ")

if confirmation.lower() != 'yes':
    print("Exiting program as per user request.")
    import sys
    sys.exit()

#============================================================================================================================================================================
###### Stage One - Extract the message details and store in supabase

def format_date(date_str):
    # Parse the input date string and format it as "Mon DD YYYY"
    dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S%z')
    formatted_date = dt.strftime('%b %d %Y')
    return formatted_date


def is_message_already_inserted(message_id):
    # Check if message with the given ID already exists in Supabase
    existing_messages = supabase_client.table(supabase_table_name).select('ID').eq('ID', message_id).execute().data
    return len(existing_messages) > 0

def process_html_to_text(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    plain_text_content = soup.get_text()
    
    # Remove emojis and icons
    emoji_pattern = re.compile("[" 
                               u"\U0001F600-\U0001F64F"  # emoticons
                               u"\U0001F300-\U0001F5FF"  # symbols & pictographs
                               u"\U0001F680-\U0001F6FF"  # transport & map symbols
                               u"\U0001F700-\U0001F77F"  # alchemical symbols
                               u"\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
                               u"\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
                               u"\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
                               u"\U0001FA00-\U0001FA6F"  # Chess Symbols
                               u"\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
                               u"\U00002702-\U000027B0"  # Dingbats
                               u"\U000024C2-\U0001F251"
                               u"\U0000200D"  
                               "]+", flags=re.UNICODE)
    
    plain_text_content = emoji_pattern.sub(r'', plain_text_content)

    # Remove extra whitespaces
    plain_text_content = re.sub(r'\s+', ' ', plain_text_content)

    return plain_text_content


def assign_image_url(sender_name):
    # Assign image URL based on sender name
    if sender_name == "The Neuron":
        return "https://media.licdn.com/dms/image/C560BAQHjLi3yEtVAjQ/company-logo_200_200/0/1676333010879/theneurondaily_logo?e=1714608000&v=beta&t=QSFDMwyfaEhkD0qy4gDeptBYInuI1_XqbV_dP8m9ux0"
    elif sender_name == "Morning Brew":
        return "https://lh3.googleusercontent.com/a-/ALV-UjVWQQJaN-3g6rRDGPqgUogO0owUKvJYvvbuZdvMHwgVO0I=s40-p"
    elif sender_name == "Axios AM PM":
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAAflBMVEX////W3OuQkJDU1NRehugoMk8iIiJZWVnR3fk7a+MzUqHIyMiEo+45ZtckJy6AgIDo7vxAbuMvRYArKyvx8fGWsPBDbNXx9f1Md+UwMDCtwfTa2tppj+lISEi2x/W8vLze5vqnp6dTfub29vY4ODhnZ2eKiorj4+N2dnactPHtQ1TEAAAAqElEQVR4AeTQxQFCMRAE0MGCfHd3779BBrekAt51ffGPVmvaQG27E0LsoXQ4ngRpUNGPhskECwq2czy6TPB8yAXH4zH0mLGGVBQzQbeYkMhbpEeyM6FssWU8B/ZMKOQ3UglUqktzxregQv6s+taAGnkLnfEWoK5nwvBz45ECXI2CfOmNuJpkz2oZ13E3MyHp8K48Uo27jaDmM2FZlhJPzXnAdKM4orIKAMZCCUXeqoMfAAAAAElFTkSuQmCC"
    elif sender_name == "Axios Vitals":
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAAflBMVEX////W3OuQkJDU1NRehugoMk8iIiJZWVnR3fk7a+MzUqHIyMiEo+45ZtckJy6AgIDo7vxAbuMvRYArKyvx8fGWsPBDbNXx9f1Md+UwMDCtwfTa2tppj+lISEi2x/W8vLze5vqnp6dTfub29vY4ODhnZ2eKiorj4+N2dnactPHtQ1TEAAAAqElEQVR4AeTQxQFCMRAE0MGCfHd3779BBrekAt51ffGPVmvaQG27E0LsoXQ4ngRpUNGPhskECwq2czy6TPB8yAXH4zH0mLGGVBQzQbeYkMhbpEeyM6FssWU8B/ZMKOQ3UglUqktzxregQv6s+taAGnkLnfEWoK5nwvBz45ECXI2CfOmNuJpkz2oZ13E3MyHp8K48Uo27jaDmM2FZlhJPzXnAdKM4orIKAMZCCUXeqoMfAAAAAElFTkSuQmCC"
    elif sender_name == "Techpresso":
        return "https://lh3.googleusercontent.com/a-/ALV-UjWBJpSjGQepBVBBlScOEGYUIb3jq2Ta06_ccdXAWK4iGQ=s40-p"
    elif sender_name == "The Average Joe":
        return "https://lh3.googleusercontent.com/a-/ALV-UjVl6y9If65LQ2Dr4UZf7tkEtS5bhuy3tQyeEtiWnbIj8A=s40-p"
    elif sender_name.startswith("TLDR"):
        return "https://lh3.googleusercontent.com/a-/ALV-UjV9qYChEzN0PJq237BhAPUv0de6kV53bxosKyo8SNzRN88=s40-p"
    elif sender_name == "Daniel Murray":
        return "https://lh3.googleusercontent.com/a-/ALV-UjWGzqQJtjsqrfVB1aqTvGzvujMv9wgy-OtLvdXn7VFzBjo=s40-p"
    elif sender_name == "Dan Primack":
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAAflBMVEX////W3OuQkJDU1NRehugoMk8iIiJZWVnR3fk7a+MzUqHIyMiEo+45ZtckJy6AgIDo7vxAbuMvRYArKyvx8fGWsPBDbNXx9f1Md+UwMDCtwfTa2tppj+lISEi2x/W8vLze5vqnp6dTfub29vY4ODhnZ2eKiorj4+N2dnactPHtQ1TEAAAAqElEQVR4AeTQxQFCMRAE0MGCfHd3779BBrekAt51ffGPVmvaQG27E0LsoXQ4ngRpUNGPhskECwq2czy6TPB8yAXH4zH0mLGGVBQzQbeYkMhbpEeyM6FssWU8B/ZMKOQ3UglUqktzxregQv6s+taAGnkLnfEWoK5nwvBz45ECXI2CfOmNuJpkz2oZ13E3MyHp8K48Uo27jaDmM2FZlhJPzXnAdKM4orIKAMZCCUXeqoMfAAAAAElFTkSuQmCC"
    elif sender_name == "CFO Brew":
        return "https://lh3.googleusercontent.com/a-/ALV-UjVWQQJaN-3g6rRDGPqgUogO0owUKvJYvvbuZdvMHwgVO0I=s40-p"
    elif sender_name == "10almonds":
        return "data:image/png;base64,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"
    elif sender_name == "Game Rant":
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAAhFBMVEVHcEwpKShMMitPVF0jFhHAZCgYERUTFx8gJjEjKDQmLTgkKTYhJjLKWgz2axPuaQ/zaw6/TwAYGygjKTUkKjYjKTb/cA/9bA+6UgsWGSEAIjnEWxT/bg0bJTLRXQwbICrTXA2eQwj4aw4eIy3yag8AIzmeTyMAJDnQWAqtSwicTiNjZ23I3EmCAAAALHRSTlMABilADSYcWsXh+/W0j+HazXQz6f/9//9WReO2/9KZfL9o9Jbq9v//e0b/XxcMPvwAAAEQSURBVHgB3ZGFAQJBDAT33d1xf+u/Py4JDhUw8D53MfwTmm4Yhg6FaQm2iRcc1/P9wAsdIIqFJM0eSl6UNyrXjurmRt20YDr5LsZiuWoeiGGXr6xZeGADCMsXCgmxqmv26g3QVbLS6bbrsjCxUcJqt99HBzISG0cOHXLGYQ7QDnUEYE9bnSx4LECx9ovAP19WsjNsEg4WOELIAt31LNAOA+/wW2ji3S7hLFMT3IQACq+sRFDcqxggSZZHHogrwpMYQFdKGZ3thOWHcBhp2WujXkLQebWBIn8XJhJOu92BPZ1n7b8INCwus22kCjzSYLx8Uys2gJnWxADC3HoBFetugXFQUHL6wECw83mecxP/yhVISypAJufpvAAAAABJRU5ErkJggg=="
    elif sender_name == "DTC Daily":
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAMAAABEpIrGAAAAwFBMVEX////Wu9zOr9afWK55AJB8AJKVPKb58fl/AJSZRamkY7KFEpmbSKuCAJaMJp6ZSqmcUKyOMaDz6vXq3O2scLnn1erv4/H79vxuAIfUuNrCm8u+ksenZrTIpNC0gsCxe73gyuSIH5yTN6WEAJS4iMOMAJWhSKuJAI+eNqPYrdS/gcHiwd+XCpmlRKi3abebAJXdttnJi8WzTqqcAI/Dd72pN6OzSKqjE5ihAJWyRKnozubFe7+3Wa6oKZ/Toc6wQaeeNcz3AAABlElEQVR4AXTOBYKEMAxA0UJSGgjuDO7c/4Jr6NrD4dNWfNL0v2liB4go930/9g3REF8UkgkSLAbbITDJBfIccPwg8PYgRAyjOIkgFehkijWRZ6wwTe7ASQvQ4FW6VBWpTCKZWgWGBV6BVYQYysRnWTchqAiKus2FS2eQ112KWa6SFpNO78qkbiO9V3gFCE3fWxIaSXFLcQ/Qx00PdAfkMDvsOPx5OLxfme/AGYw/9I/AMH+z3UdAf3EegWn/4TnCP65gPNdgPPF4BnIc7C89TKeyLOMrGE9SF6einMS8HME6b8uXuRaXaFGP4LC+tzkeCQyCQBR1xzp9m+3YdSJ+rPe/VQZUIOXR+Y9CPn+k2Tkvwg2FIw9CKS0I+S5UZJe1dM1Zuqr1Qp5XFiabvZIkEykWqq7Vll6EO91JNS6o9C5UO2AR5HwqzYJD4KrTDlByq+US9SsYB0gu8DzYC6jgYBqyINAhKMb+RF+PIVfAtE9n9BvQd59nAC/7/Mnd6pjRamO0NtqAAXi75n/MKvpwRj8MW/QGCGhHxjqbIAMAAAAASUVORK5CYII="
    else:
        # Default image URL for other senders
        return "https://lh3.googleusercontent.com/a/ACg8ocLTKNXKQDxO5YZoWBmIyCTW0ysz8KkMUkJUfCsDMO6Xlg=s260-c-no"
    


# USING ALL THE ABOVE FUCNTIONS HERE BELOW

def get_affiliate_link(sender_name):

    affiliate_links = {
        "Dan Primack": "https://fbuy.io/axios/naga4898",
        "Axios Vitals": "https://fbuy.io/axios/naga4898",
        "Axios AM PM": "https://fbuy.io/axios/naga4898",
        "The Average Joe": "https://sparklp.co/p/84632131e3",
        "The Neuron": "https://www.theneurondaily.com/subscribe?ref=hftueGis0K",
        "Techpresso": "http://dupple.com/?utm_source=tool&utm_medium=app&utm_campaign=naga",
        "TLDR": "https://tldr.tech/ai?ref=5193639",
        "Morning Brew": "https://www.morningbrew.com/daily/r?kid=26c0c2be",
        "CFO Brew": "https://www.cfobrew.com/r?kid=26c0c2be",
        "Daniel Murray": "https://tmm.workweek.com/68f86643/10",
        "10almonds": "https://10almonds.com/",
        "Game Rant": "https://gamerant.com/",
        "DTC Daily": "https://dtcdaily.beehiiv.com/subscribe?ref=hftueGis0K"   
    }

    default_affiliate_link = "https://www.wikipedia.org/"

    if sender_name.startswith("TLDR"):
        return affiliate_links.get("TLDR", default_affiliate_link)
    else:
        return affiliate_links.get(sender_name, default_affiliate_link)
    
def get_publisher_id(sender_str):
    sender_mapping = {
        'TLDR AI': 10,
        'Techpresso': 11,
        'TLDR': 12,
        'The Neuron': 13,
        'CFO Brew': 20,
        'The Average Joe': 21,
        'Dan Primack': 22,
        'Game Rant': 30,
        '10almonds': 40,
        'Axios Vitals': 41,
        'Daniel Murray': 50,
        'DTC Daily': 51,
        'TLDR Marketing': 52,
        'Morning Brew': 60,
        'Mike Allen': 61
    }

    # Default to None if sender_str not found in mapping
    return sender_mapping.get(sender_str, None)

def store_message_in_supabase(message):
    try:
        # Convert attributes to strings
        sender_str = extract_name_from_sender(str(message.sender))
        id_str = str(message.id)
        subject_str = str(message.subject)
        date_str = format_date(str(message.date))
        date_time_str = str(message.date)


        # Check if the message is already inserted
        if is_message_already_inserted(id_str):
            print(f"Skipping duplicate message with ID: {id_str}_{sender_str}_{date_str}")
            return

        # Process and store body content
        plain_text_content = process_html_to_text(message.html)
        plain_text_content = sender_str + " " +"Newsletter" + "-" + plain_text_content
        # Assign image URL based on sender name
        image_url = assign_image_url(sender_str)

        # Extract affiliate link based on sender name using the function
        affiliate_link = get_affiliate_link(sender_str)

        # Get sender category
        sender_category = get_sender_category(sender_str)

        # publisher identification
        publisher_id = get_publisher_id(sender_str)

        # Insert data into Supabase table
        supabase_data = {
            "ID": id_str,
            "from": sender_str,
            "subject": subject_str,
            "received_day": date_str,
            "received_date_time": date_time_str,
            "body": plain_text_content,
            "image_url": image_url,
            "affiliate_links": affiliate_link,
            "publisher_id": publisher_id,
            "category": sender_category
        }

        data = supabase_client.table(supabase_table_name).insert([supabase_data]).execute()
        print(f"Details of {sender_str} saved successfully")
        # Assert data insertion success
        assert len(data.data) > 0

    except Exception as e:
        print(f"Error storing message in Supabase: {e}")
        traceback.print_exc()

#============================================================================================================================================================================
    

def extract_href_from_html(html, link_text):
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all 'a' tags with or without 'span'
    a_tags = soup.find_all('a')

    # Extract cleaned text content of the 'a' tags
    a_texts = [re.sub(r'\s+', ' ', tag.get_text(strip=True)) for tag in a_tags]

    # Find all 'a' tags with the specified link text in the cleaned text
    links = [tag['href'] for tag, text in zip(a_tags, a_texts) if link_text in text]

    if links:
        return links
    else:
        print(f"No hrefs with text '{link_text}' found in the HTML.")
        return None    
    
def extract_and_remove_admin_specific_links_from_messages(soup, keywords, browser_redirect):
    a_tags = soup.find_all('a')
    a_texts = [re.sub(r'\s+', ' ', tag.get_text(strip=True)) for tag in a_tags]

    filtered_links = {}
    for keyword in keywords:
        filtered_links[keyword] = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape(keyword), text, re.IGNORECASE)]

    browser_redirect_links = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape(browser_redirect), text, re.IGNORECASE)]

    for link_list in filtered_links.values():
        for link in link_list:
            if soup.find('a', href=link):
                soup.find('a', href=link).decompose()

    for link in browser_redirect_links:
        if soup.find('a', href=link):
            soup.find('a', href=link).decompose()

def read_website_content(url, browser_redirect, timeout=30):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

    try:
        response = requests.get(url, headers=headers, allow_redirects=True, timeout=timeout)
        response.raise_for_status()  # Raises HTTPError for bad responses
        soup = BeautifulSoup(response.text, 'html.parser')

        keywords = ["nagakowshaltata@gmail.com", "Unsubscribe", "Manage", "here", browser_redirect]  # Include browser_redirect in keywords
        extract_and_remove_admin_specific_links_from_messages(soup, keywords, browser_redirect)

        content = soup.prettify()
        content = re.sub(r'\s+', ' ', content)

        return content

    except requests.exceptions.Timeout:
         print(f"Timeout exceeded while fetching content from {url}")
         return f"<html><body><p>Timeout exceeded while fetching content</p><p>You can try redirecting to the {url}</p></body></html>", None

    except requests.exceptions.RequestException as e:
        try:
            soup = BeautifulSoup(message.html, 'html.parser')
            # Remove last 10 <a> tags
            last_10_a_tags = soup.find_all('a')[-10:]
            for tag in last_10_a_tags:
                tag.decompose()

            keywords = ["nagakowshaltata@gmail.com", "Unsubscribe", "Manage", "here", browser_redirect] 
            extract_and_remove_admin_specific_links_from_messages(soup, keywords, browser_redirect)


            content = soup.prettify()
            content = re.sub(r'\s+', ' ', content)

            return content

        except Exception as e:
            raise RuntimeError(f"Error parsing alternative HTML content: {str(e)}")

    except Exception as e:
        raise RuntimeError(f"Error fetching website content from {url}: {str(e)}")

# def read_website_content(url, browser_redirect, timeout=30):
#     headers = {
#         'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
#     }

#     try:
#         response = requests.get(url, headers=headers, allow_redirects=True, timeout=timeout)
#         if response.status_code == 200:
            
#             soup = BeautifulSoup(response.text, 'html.parser')

#             # Extract and remove links with text "Unsubscribe" (case-insensitive)
#             a_tags = soup.find_all('a')
#             a_texts = [re.sub(r'\s+', ' ', tag.get_text(strip=True)) for tag in a_tags]
#             emaillinks = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape("nagakowshaltata@gmail.com"), text, re.IGNORECASE)]
#             unsubscribe_links = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape("Unsubscribe"), text, re.IGNORECASE)]
#             manage_links = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape("Manage"), text, re.IGNORECASE)]
#             browser_redirect_links = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape(browser_redirect), text, re.IGNORECASE)]

#             # last_10_a_tags = a_tags[-15:]
#             # for tag in last_10_a_tags:
#             #     tag.decompose()

#             for link in unsubscribe_links:
#                 if soup.find('a', href=link):
#                     soup.find('a', href=link).decompose()

#             for link in emaillinks:
#                 if soup.find('a', href=link):
#                     soup.find('a', href=link).decompose()  

#             for link in manage_links:
#                 if soup.find('a', href=link):
#                     soup.find('a', href=link).decompose()   

#             for link in browser_redirect_links:
#                 if soup.find('a', href=link):
#                     soup.find('a', href=link).decompose()

#             content = soup.prettify()
#             # Ensure only one space between each word
#             content = re.sub(r'\s+', ' ', content)

#             return content
#         else:
#             soup = BeautifulSoup(message.html, 'html.parser')

#             # Extract and remove links with text "Unsubscribe" (case-insensitive)
#             a_tags = soup.find_all('a')
#             a_texts = [re.sub(r'\s+', ' ', tag.get_text(strip=True)) for tag in a_tags]
#             emaillinks = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape("nagakowshaltata@gmail.com"), text, re.IGNORECASE)]
#             unsubscribe_links = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape("Unsubscribe"), text, re.IGNORECASE)]
#             manage_links = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape("Manage"), text, re.IGNORECASE)]
#             click_here_links = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape("here"), text, re.IGNORECASE)]
#             browser_redirect_links = [tag['href'] for tag, text in zip(a_tags, a_texts) if re.search(re.escape(browser_redirect), text, re.IGNORECASE)]

#             last_10_a_tags = a_tags[-15:]
#             for tag in last_10_a_tags:
#                 tag.decompose()

#             for link in unsubscribe_links:
#                 if soup.find('a', href=link):
#                     soup.find('a', href=link).decompose()

#             for link in emaillinks:
#                 if soup.find('a', href=link):
#                     soup.find('a', href=link).decompose()  

#             for link in manage_links:
#                 if soup.find('a', href=link):
#                     soup.find('a', href=link).decompose()   

#             for link in click_here_links:
#                 if soup.find('a', href=link):
#                     soup.find('a', href=link).decompose()

#             for link in browser_redirect_links:
#                 if soup.find('a', href=link):
#                     soup.find('a', href=link).decompose()

#             content = soup.prettify()
#             # Ensure only one space between each word
#             content = re.sub(r'\s+', ' ', content)

#             return content#f"<html><body><p>Error fetching website content from <a href='{url}'>{url}</a></p></body></html>"
#     except requests.exceptions.Timeout:
#         print(f"Timeout exceeded while fetching content from {url}")
#         return f"<html><body><p>Timeout exceeded while fetching content</p><p>You can try redirecting to the {url}</p></body></html>", None
#     except Exception as e:
#         return f"Error: {str(e)}", None
    

def update_html_content_in_supabase(message):
    id_str = str(message.id)
    
    # Get the existing data for the specified ID
    existing_data = supabase_client.table(supabase_table_name).select('ID', 'html').eq('ID', id_str).execute().data
    
    if len(existing_data) == 0:
        print(f"Message with ID {id_str} not found in Supabase.")
        return
    
    # Extract sender name
    sender_str = extract_name_from_sender(str(message.sender))

    # Initialize browser_redirect with a default value
    browser_redirect = None

    # Extract web redirect URLs based on sender
    if sender_str == "Techpresso":
        browser_redirect = "View online"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[-1]  # Get the last found href
        else:
            print("No Hrefs found for 'View online'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "The Neuron":
        browser_redirect = "Read Online"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[0]  # Get the first found href
        else:
            print("No Hrefs found for 'Read Online'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "Morning Brew":
        browser_redirect = "View Online"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[0]  # Get the first found href
        else:
            print("No Hrefs found for 'View Online'. Using default Href.")
            url = "http://example.in/"

    elif sender_str.startswith("TLDR"):
        browser_redirect = "View Online"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[0]  # Get the first found href
        else:
            print("No Hrefs found for 'View Online'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "The Average Joe":
        browser_redirect = "View in browser"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[0]  # Get the first found href
        else:
            print("No Hrefs found for 'View in browser'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "Dan Primack":
        browser_redirect = "View in browser"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[0]  # Get the first found href
        else:
            print("No Hrefs found for 'View in browser'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "Axios AM PM":
        browser_redirect = "View in browser"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[0]  # Get the first found href
        else:
            print("No Hrefs found for 'View in browser'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "Axios Vitals":
        browser_redirect = "View in browser"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[0]  # Get the first found href
        else:
            print("No Hrefs found for 'View in browser'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "CFO Brew":
        browser_redirect = "View Online"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[0]  # Get the first found href
        else:
            print("No Hrefs found for 'View Online'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "DTC Daily":
        browser_redirect = "Read Online"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[0]  # Get the last found href
        else:
            print("No Hrefs found for 'View Online'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "Daniel Murray":
        browser_redirect = "View online"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[-1]  # Get the last found href
        else:
            print("No Hrefs found for 'View Online'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "10almonds":
        browser_redirect = "Read Online"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[-1]  # Get the last found href
        else:
            print("No Hrefs found for 'View Online'. Using default Href.")
            url = "http://example.in/"

    elif sender_str == "Game Rant":
        browser_redirect = "ReadOnline"
        hrefs = extract_href_from_html(message.html, browser_redirect)
        if hrefs:
            url = hrefs[-1]  # Get the last found href
        else:
            print("No Hrefs found for 'View Online'. Using default Href.")
            url = "http://example.in/"
    else:
        print(f"Sender {sender_str} not recognized. Using default Href.")
        url = "http://example.in/"
    
    # Save the open in gmail link to into the 'View_in_gmail' column
    # Update the data in Supabase with the specified URL
    gmail_link = "https://mail.google.com/mail/u/0/#search/subject:" + message.subject
    supabase_client.table(supabase_table_name).update({
        'view_in_gmail': gmail_link
    }).eq('ID', id_str).execute()
    

    # Read website content and get prettified HTML
    extracted_html = read_website_content(url,browser_redirect)
    
    # Update the data in Supabase with prettified HTML
    data = supabase_client.table(supabase_table_name).update({
        'html': extracted_html
    }).eq('ID', id_str).execute()

    print(f"Html of {sender_str} saved successfully")
    # Assert data update success

    assert len(data.data) > 0



#============================================================================================================================================================================
# Store each message details in Supabase
for message in Messages:
    store_message_in_supabase(message)
    

for message in Messages:
    # Update HTML content for the message using its ID
    update_html_content_in_supabase(message)
    


#============================================================================================================================================================================
## Stage two summarize body and generate audio file and generate summary_image

personality = personality_env

def generate_summary(plain_text_content):
    response = openai_client.chat.completions.create(
        model= gpt_model,
        messages = [
            {"role": "system", "content": f"{personality}"},
            {"role": "user", "content": plain_text_content}
        ]
    )

    total_tokens = response.usage.total_tokens
    summary = response.choices[0].message.content

    # Clean up the response
    summary = summary.replace('\n', ' ')
    summary = summary.replace('\\', '')
    summary = re.sub(r'\*+', '', summary)

    return summary, total_tokens


# Function to upload MP3 file to Supabase storage
def upload_mp3(file_path, saved_filename):
    with open(file_path, 'rb') as file:
        response = supabase_client.storage.from_("Summary_Voice").upload(
            file=file,
            path=f"{saved_filename}",
            file_options={"content-type": "audio/mpeg"}
        )
        print(f'File uploaded successfully: {saved_filename}')
 

# Function to get public URL
def get_file_url(file_name):
    public_url = supabase_client.storage.from_("Summary_Voice").get_public_url(file_name)
    return public_url

# Function to generate word cloud from body_summary
def generate_word_cloud(body_summary, id_str, sender_str, date_str):
    word_cloud_text = body_summary
    # background_color = np.random.choice(['white', 'black', 'gray', 'blue']) #, 'orange'
    # colormap = np.random.choice(['viridis', 'plasma', 'inferno', 'magma', 'cividis', 'Blues', 'Reds', 'coolwarm','Oranges', 'twilight', 'tab10', "twilight_shifted", "hsv"])
    colormap = np.random.choice(['viridis', 'plasma', 'inferno', 'magma', 'cividis',  'Reds', "Purples",'Oranges', 'twilight', 'tab10',"seismic","Set1"])

    # Generate the word cloud with dynamically generated random colors and excluding stop words
    wordcloud = WordCloud(
        width=800,
        height=400,
        # background_color="#292a2e",
        background_color=background_color,
        stopwords=set(STOPWORDS),
        collocations=False,
        colormap=colormap,
        contour_width=np.random.uniform(0.5, 3.0),  # Random width for the contour
        contour_color=np.random.choice(['black', 'white', 'gray', 'red', 'blue'])
    ).generate(word_cloud_text)

    # Display the generated word cloud using Matplotlib (optional)
    plt.figure(figsize=(10, 5))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')
    plt.tight_layout()
    plt.savefig(f"word_cloud/{id_str}_{sender_str}_{date_str}_wordcloud.png")

    # Save the word cloud image to the same folder
    wordcloud.to_file(f"word_cloud/{id_str}_{sender_str}_{date_str}_wordcloud.png")

    # Upload the word cloud image to Supabase Storage
    with open(f"word_cloud/{id_str}_{sender_str}_{date_str}_wordcloud.png", 'rb') as file:
        response = supabase_client.storage.from_("summary_image").upload(
            file=file,
            path=f"{id_str}_{sender_str}_{date_str}_wordcloud.png",
            file_options={"content-type": "image/png"}
        )
        print(f'Word cloud image uploaded successfully for message {id_str}_{sender_str}_{date_str}')

    # Get public URL for the uploaded word cloud image
    public_url = supabase_client.storage.from_("summary_image").get_public_url(f"{id_str}_{sender_str}_{date_str}_wordcloud.png")

    # Update Supabase with the public URL for the word cloud image
    update_url_query = supabase_client.table(supabase_table_name).update({
        'summary_image': public_url
    }).eq('ID', id_str).execute()


# Iterate over records and generate summaries
for message in Messages:
    # Convert attributes to strings
    sender_str = extract_name_from_sender(message.sender)
    id_str = str(message.id)
    date_str = format_date(str(message.date))

    # Fetch existing record from Supabase
    existing_record = supabase_client.table(supabase_table_name).select('ID', 'body_summary').eq('ID', id_str).execute().data

    # Check if the record with the given ID exists
    if not existing_record:
        print(f"Skipping message {id_str} because ID not found in Supabase.")
        continue

    # Check if the body_summary of this record is empty
    if existing_record and not existing_record[0]['body_summary']:
        # Prepare user input for OpenAI API
        plain_text_content = process_html_to_text(message.html)
        plain_text_content = sender_str + " " +"Newsletter" + "-" + plain_text_content 


        # Generate summary using OpenAI Assistance API
        summary, total_tokens = generate_summary(plain_text_content)

        # Update Supabase with the generated summary and token count
        update_summary_query = supabase_client.table(supabase_table_name).update({
            'body_summary': summary,
            'summary_token_count': total_tokens
        }).eq('ID', id_str).execute()


        # Generate word cloud
        generate_word_cloud(summary, id_str, sender_str, date_str)

        # Generate voice file using OpenAI TTS
        voice_filename = f"{id_str}_{sender_str}_{date_str}.mp3"
        # Set the text to be synthesized
        synthesis_input = texttospeech.SynthesisInput(text=summary)

        # Set the voice and audio configuration
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name="en-US-Studio-O"
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            effects_profile_id=["headphone-class-device"],
            pitch=0,
            speaking_rate=1
        )

        # Create a Text-to-Speech client
        client = texttospeech.TextToSpeechClient()

        # Perform the text-to-speech request
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )

        # Specify the folder name where you want to save the audio files
        output_folder = "audio_summary"

        # Save the audio to a file in the specified folder
        output_file = os.path.join(output_folder, voice_filename)
        with open(output_file, "wb") as out_file:
            out_file.write(response.audio_content)
            print(f'Audio content written to "{output_file}"')

        # Upload MP3 file to Supabase storage
        upload_mp3(output_file, f"{id_str}_{sender_str}_{date_str}.mp3")

        # Get public URL
        public_url = get_file_url(f"{id_str}_{sender_str}_{date_str}.mp3")

        # Update Supabase with the public URL
        update_url_query = supabase_client.table(supabase_table_name).update({
            'audio_url': public_url
        }).eq('ID', id_str).execute()

    else:
        print(f"Skipping message {id_str} because Body_Summary is not empty.")