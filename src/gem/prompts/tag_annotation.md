Determine whether the following text contains multi-step operations involving the use of an APP, website, computer, or other machine (such as robot, elevator, etc), if contains, generate one sentence summary of the task and identify the platform, domain and task category of the multi-step task.

# Detaild Instruction
1. Platform category: operator, computer, phone, machine, other
2. Domain category: adult, arts_and_entertainment, autos_and_vehicles, beauty_and_fitness, books_and_literature, business_and_industrial, computers_and_electronics, finance, food_and_drink, games, health, hobbies_and_leisure, home_and_garden,internet_and_telecom, jobs_and_education, law_and_government, news, online_communities, people_and_society, pets_and_animals, real_estate, science, sensitive_subjects, shopping, sports, travel_and_transportation
3. Task category: databases, multimedia_processing, cloud_platforms, calendar_management, cryptocurrency, location_services, communication, search, file_systems, web_scraping, ecommerce_and_retail, customer_data_platforms, developer_tools, virtualization, version_control, research_and_data, aigc, travel_and_transportation, note_taking, language_translation, rag_systems, security_and_iam, social_media, monitoring, weather_services, customer_support, blockchain, knowledge_and_memory, financial_trading, marketing, enterprise_business_intelligence, transportation_logistics, iphone_android, smart_home, education_elearning, robot_control, website_control, gaming_entertainment

# Input
{text}

# Output Format
<multi_step>False</multi_step>
Or:
<multi_step>True</multi_step>
<summary>xxx</summary>
<domain>Shopping, Sports</domain>
<platform>Operator</platform>
<task>customer_support</task>