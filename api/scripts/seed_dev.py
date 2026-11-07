"""Demo data so the website, leaderboard and agents have something real to show.

Safe to run again: everything is added only if missing, and the worked-example settings are
re-applied. Adds:
- the four categories, with two or more tagged projects in each (filters, exclusions and the chat),
  each with the group that runs it (its facilitator): 76 projects in Kenya and around the world
  (Palestine, Syria, Yemen, DR Congo, Ukraine, Haiti, Bangladesh, the Pacific, the Americas, Europe...).
  New ones go in Health, Water or Environment: an unbacked Education project would change the worked
  example's floor shares. Their milestones add up to their goals.
- the System Design worked example in Education: the four projects with goals big enough that
  the 40% category cap binds, and their seeded backers (16 x 12.50, 9 x 12.50, 4 x 50 USD), so the
  leaderboard shows Lanet Library capped and its excess shared out
- 3 or 4 dated milestones per project (the timeline and the admin's held tranches): Lanet Library's
  first, a 30 USD tranche, stays open to try a real payout; Kaptembwo Desks and Girls' STEM Club
  each have a released tranche (a story on the website), Girls' STEM Club one with evidence being
  checked, Kaptembwo Desks one held for an admin. Released tranches are booked like a real release
  but paid in the database only: their payout batch stays PENDING under a SEED- batch id, so nothing
  goes to PayPal and reconciliation stays clean (there is no PayPal money behind seeded backers).
- a demo donor for the Giving Agent page (there is no route that creates donors), id 1 on a fresh database
- an open round: 10,000 USD pool, 40% cap

Seeded backers are database rows, not PayPal payments; reconciliation only counts PayPal money.

The SQLite file is relative to where the API starts, so run this from the same folder:
    from api/:      .venv/Scripts/python -m scripts.seed_dev
    from the root:  PYTHONPATH=api api/.venv/Scripts/python -m scripts.seed_dev
Against Render: set DATABASE_URL to the External Database URL for that one command.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.db import SessionLocal, create_schema, engine
from app.models import (
    Category,
    Donation,
    DonationStatus,
    Donor,
    DocumentKind,
    LedgerEntry,
    LedgerType,
    Milestone,
    MilestoneStatus,
    Payout,
    PayoutStatus,
    Project,
    ProjectDocument,
    ProjectStatus,
    Round,
    RoundStatus,
    TargetType,
)

# (category, title, tags, cause, beneficiary group, region, urgency, goal cents, summary)
PROJECTS = [
    # The worked example: goals leave room above each project's share, so only the 40% cap binds.
    ("Education", "Lanet Library", ["books", "literacy"], "literacy", "children", "Nakuru", 4, 600_000,
     "A lending library for three primary schools in Lanet: shelves, 400 books and a part-time librarian."),
    ("Education", "Kaptembwo Desks", ["furniture", "schools"], "school equipment", "children", "Nakuru", 3, 400_000,
     "Forty double desks for Kaptembwo Primary, where pupils share benches or sit on the floor."),
    ("Education", "Girls' STEM Club", ["stem", "girls"], "stem education", "youth", "Kisumu", 3, 300_000,
     "Weekly science and coding sessions for 30 secondary-school girls, with kits and a mentor."),
    ("Education", "New Reading Corner", ["books"], "literacy", "children", "Eldoret", 5, 150_000,
     "A reading corner with mats, shelves and 150 picture books for an Eldoret nursery school."),
    ("Health", "Mobile Eye Clinic", ["eye-care", "screening"], "primary care", "elderly", "Turkana", 4, 500_000,
     "Monthly eye screening and free reading glasses in four Turkana villages."),
    ("Health", "St. Mary's Mission Maternity Ward", ["faith-based", "maternal-health"], "maternal care", "adults",
     "Kisumu", 3, 450_000, "Two delivery beds and a solar fridge for a faith-run maternity ward."),
    ("Health", "Lupus Patient Support Fund", ["rare-disease", "medicine"], "rare diseases", "adults", "Nairobi", 2,
     800_000, "Medicine and transport to specialist clinics for 25 people living with lupus."),
    ("Environment", "Lake Shoreline Trees", ["trees", "climate"], "conservation", "community", "Kisumu", 3, 500_000,
     "Planting 2,000 indigenous trees along Lake Victoria's eroding shoreline, with local youth groups."),
    ("Environment", "Plastic-Free Market", ["recycling", "waste"], "waste", "community", "Mombasa", 2, 250_000,
     "Collection points and reusable bags for Kongowea market's traders."),
    ("Water", "Village Borehole Repair", ["water", "infrastructure"], "clean water", "community", "Turkana", 5, 350_000,
     "Repairing a broken borehole pump that served 600 people, and training two local mechanics."),
    ("Water", "School Rainwater Tanks", ["water", "schools"], "clean water", "children", "Eldoret", 3, 200_000,
     "Two 10,000-litre rain tanks and gutters so pupils have water at school all year."),
    # Outside Kenya: the platform isn't tied to one country (Health, Water, Environment only, so the
    # Education worked example above is unchanged)
    ("Water", "Dhaka Household Water Filters", ["water", "health"], "clean water", "families", "Dhaka", 4, 300_000,
     "Ceramic water filters and training for 120 households in a flood-prone Dhaka neighbourhood."),
    ("Health", "Lima Community Dental Van", ["dental", "screening"], "primary care", "children", "Lima", 3, 400_000,
     "A monthly dental check-up van for six schools on the edge of Lima, with fluoride and referrals."),
    ("Environment", "Manila Bay Mangrove Replanting", ["trees", "climate"], "conservation", "community", "Manila", 3,
     350_000, "Replanting 3,000 mangrove seedlings along Manila Bay with local fisherfolk groups."),
    # Around the world: outside Education, so the worked example above stays exactly as designed.
    ("Health", "Gaza Field Clinic Medical Supplies", ["medicine", "emergency"], "emergency care", "community", "Gaza", 5, 600_000,
     "Wound-care kits, antibiotics and insulin for a community field clinic in Gaza City serving 3,000 patients a month."),
    ("Water", "Gaza Household Water Deliveries", ["water", "emergency"], "clean water", "families", "Gaza", 5, 450_000,
     "Trucked drinking water and storage jerrycans for 400 displaced families in Deir al-Balah, Gaza."),
    ("Health", "Adré Child Nutrition Centre", ["nutrition", "refugees"], "nutrition", "children", "Adré", 5, 500_000,
     "Therapeutic food and weekly screening for malnourished children among Sudanese refugees in Adré, Chad."),
    ("Water", "Sana'a Neighbourhood Water Filters", ["water", "health"], "clean water", "families", "Sana'a", 4, 250_000,
     "Household water filters and cholera-prevention training for 200 families in Sana'a, Yemen."),
    ("Health", "Port-au-Prince Cholera Prevention", ["water", "screening"], "disease prevention", "community", "Port-au-Prince", 4, 300_000,
     "Oral rehydration points and chlorine tablets in three Port-au-Prince neighbourhoods, Haiti."),
    ("Health", "Kharkiv Mobile Physiotherapy", ["rehabilitation", "disability"], "rehabilitation", "adults", "Kharkiv", 4, 450_000,
     "A physiotherapy van visiting people recovering from injuries in villages around Kharkiv, Ukraine."),
    ("Water", "Sindh Flood-Safe Hand Pumps", ["water", "infrastructure"], "clean water", "community", "Sindh", 4, 350_000,
     "Raised hand pumps that stay usable in floods for eight villages in Dadu district, Sindh, Pakistan."),
    ("Water", "Oaxaca Rainwater Harvesting", ["water", "schools"], "clean water", "children", "Oaxaca", 3, 220_000,
     "Rainwater tanks and filters for five rural schools in the Mixteca region of Oaxaca, Mexico."),
    ("Environment", "Amazon Riverbank Reforestation", ["trees", "climate"], "conservation", "community", "Pará", 3, 400_000,
     "Replanting 5,000 native trees along eroding riverbanks with riverside families in Pará, Brazil."),
    ("Environment", "Lagos Lagoon Plastic Cleanup", ["recycling", "waste"], "waste", "community", "Lagos", 3, 280_000,
     "Monthly lagoon cleanups and a plastic buy-back point for fishing families in Makoko, Lagos, Nigeria."),
    ("Environment", "Fiji Coral Reef Restoration", ["coral", "climate"], "conservation", "community", "Suva", 3, 320_000,
     "Coral nurseries and reef replanting with fishing villages near Suva, Fiji."),
    ("Environment", "Kathmandu Valley Clean Cookstoves", ["air-quality", "climate"], "clean air", "families", "Kathmandu", 3, 240_000,
     "Efficient cookstoves for 300 households to cut indoor smoke in villages around Kathmandu, Nepal."),
    ("Health", "Gaza Children's Trauma Counselling", ["mental-health", "emergency"], "mental health", "children", "Gaza", 5, 300_000,
     "Group counselling and play sessions for 600 children in Khan Younis shelters, Gaza."),
    ("Health", "Gaza Dialysis Patient Transport", ["medicine", "emergency"], "chronic care", "adults", "Gaza", 5, 360_000,
     "Safe transport three times a week for 80 kidney patients to reach dialysis in central Gaza."),
    ("Water", "West Bank Village Cisterns", ["water", "infrastructure"], "clean water", "families", "Hebron Hills", 4, 300_000,
     "Repairing rainwater cisterns for 60 herding families in the South Hebron Hills, West Bank."),
    ("Health", "Beirut Elderly Home Visits", ["elderly-care", "medicine"], "elderly care", "elderly", "Beirut", 3, 370_000,
     "Nurse home visits and medicine for 150 isolated older people in Beirut, Lebanon."),
    ("Health", "Idlib Mobile Maternity Unit", ["maternal-health", "emergency"], "maternal care", "adults", "Idlib", 5, 480_000,
     "A mobile maternity unit for camps around Idlib, Syria: antenatal checks, safe deliveries and newborn care."),
    ("Water", "Mosul Water Network Repair", ["water", "infrastructure"], "clean water", "community", "Mosul", 4, 400_000,
     "Fixing broken water mains so 2,000 households in west Mosul, Iraq, get running water again."),
    ("Environment", "Amman Rooftop Gardens", ["gardens", "climate"], "urban farming", "families", "Amman", 2, 130_000,
     "Rooftop vegetable gardens with drip irrigation for 50 refugee and host families in Amman, Jordan."),
    ("Environment", "Atlas Mountains Terrace Rebuilding", ["soil", "climate"], "land restoration", "community", "Al Haouz", 3, 300_000,
     "Rebuilding earthquake-damaged farm terraces and planting almond trees in Al Haouz, Morocco."),
    ("Health", "Taiz Cholera Treatment Corner", ["medicine", "emergency"], "disease prevention", "community", "Taiz", 5, 260_000,
     "An oral rehydration corner and cholera beds at a district health centre in Taiz, Yemen."),
    ("Health", "Kabul Midwife Training", ["maternal-health", "training"], "maternal care", "adults", "Kabul", 4, 330_000,
     "Training 20 community midwives and stocking delivery kits for districts around Kabul, Afghanistan."),
    ("Health", "Goma Displacement Camp Clinic", ["medicine", "refugees"], "primary care", "community", "Goma", 5, 400_000,
     "Basic medicines and a nurse for a clinic serving displaced families near Goma, DR Congo."),
    ("Water", "Tigray Spring Protection", ["water", "infrastructure"], "clean water", "community", "Tigray", 4, 260_000,
     "Capping and protecting six mountain springs that supply 3,000 people in Tigray, Ethiopia."),
    ("Health", "Mogadishu Child Vaccination Days", ["vaccines", "screening"], "disease prevention", "children", "Mogadishu", 4, 200_000,
     "Cold boxes, outreach and catch-up vaccination days for children in Mogadishu's settlements, Somalia."),
    ("Environment", "Sahel Great Green Wall Plots", ["trees", "climate"], "land restoration", "community", "Tillabéri", 3, 260_000,
     "Half-moon basins and drought-tolerant trees to bring back degraded farmland in Tillabéri, Niger."),
    ("Water", "Turkana Solar Water Kiosk", ["water", "solar"], "clean water", "community", "Lodwar", 4, 320_000,
     "A solar-powered water kiosk with a treatment unit for a fast-growing settlement near Lodwar, Kenya."),
    ("Health", "Kibera Sickle Cell Clinic Day", ["rare-disease", "screening"], "chronic care", "children", "Nairobi", 3, 200_000,
     "A monthly sickle cell clinic day with screening, folic acid and pain care for children in Kibera."),
    ("Environment", "Lake Victoria Water Hyacinth Removal", ["waste", "climate"], "conservation", "community", "Kisumu", 3, 180_000,
     "Clearing water hyacinth from fishing landing sites and turning it into briquettes, Kisumu, Kenya."),
    ("Health", "Freetown Maternal Blood Bank", ["maternal-health", "medicine"], "maternal care", "adults", "Freetown", 4, 240_000,
     "A blood fridge and donor drives so mothers who bleed after birth can get a transfusion, Freetown, Sierra Leone."),
    ("Water", "Malawi Flood-Proof Boreholes", ["water", "infrastructure"], "clean water", "community", "Chikwawa", 4, 320_000,
     "Raised, flood-proof boreholes for four villages in Chikwawa, Malawi, after repeated floods."),
    ("Environment", "Madagascar Mangrove Nurseries", ["trees", "coral"], "conservation", "community", "Mahajanga", 3, 180_000,
     "Mangrove nurseries run by fishing villages to protect the coast near Mahajanga, Madagascar."),
    ("Health", "Kampala Disability Wheelchair Workshop", ["disability", "rehabilitation"], "rehabilitation", "adults", "Kampala", 3, 230_000,
     "A workshop building and fitting 60 wheelchairs made for rough roads, Kampala, Uganda."),
    ("Water", "Juba School Handwashing Stations", ["water", "schools"], "hygiene", "children", "Juba", 4, 140_000,
     "Handwashing stations and soap for 12 primary schools in Juba, South Sudan."),
    ("Health", "Cox's Bazar Camp Eye Care", ["eye-care", "refugees"], "primary care", "elderly", "Cox's Bazar", 4, 320_000,
     "Cataract screening and surgery for older Rohingya refugees in Cox's Bazar, Bangladesh."),
    ("Water", "Sylhet Arsenic-Safe Wells", ["water", "health"], "clean water", "families", "Sylhet", 4, 250_000,
     "Testing wells for arsenic and drilling deep safe wells for 10 villages in Sylhet, Bangladesh."),
    ("Environment", "Sundarbans Embankment Planting", ["trees", "climate"], "conservation", "community", "Satkhira", 3, 190_000,
     "Planting mangroves and grasses to strengthen river embankments in the Sundarbans, Bangladesh."),
    ("Health", "Rakhine Mobile Health Boat", ["medicine", "screening"], "primary care", "community", "Sittwe", 4, 330_000,
     "A boat clinic reaching riverside villages around Sittwe, Myanmar, every two weeks."),
    ("Water", "Mekong Delta Salt-Free Water Tanks", ["water", "climate"], "clean water", "families", "Ben Tre", 3, 300_000,
     "Large rain tanks so families in Ben Tre, Vietnam, have fresh water when seawater pushes up the rivers."),
    ("Environment", "Borneo Orangutan Corridor Replanting", ["trees", "wildlife"], "conservation", "community", "Sabah", 3, 250_000,
     "Replanting a forest corridor between reserves with villagers along the Kinabatangan River, Sabah, Malaysia."),
    ("Health", "Mindanao Typhoon Clinic Rebuild", ["medicine", "infrastructure"], "primary care", "community", "Surigao", 4, 280_000,
     "Rebuilding a village health station damaged by a typhoon in Surigao del Norte, Philippines."),
    ("Environment", "Tuvalu Coastal Seawall Plants", ["climate", "coral"], "climate adaptation", "community", "Funafuti", 4, 180_000,
     "Native coastal plants and a living seawall to slow erosion on Funafuti, Tuvalu."),
    ("Health", "Papua New Guinea Village Birth Kits", ["maternal-health", "medicine"], "maternal care", "adults", "Mount Hagen", 4, 160_000,
     "Clean birth kits and training for village birth attendants in the highlands near Mount Hagen, Papua New Guinea."),
    ("Water", "Ladakh Ice Stupa Water Storage", ["water", "climate"], "water storage", "community", "Leh", 2, 150_000,
     "Artificial glaciers that store winter water for spring irrigation in villages near Leh, Ladakh, India."),
    ("Health", "Chennai Street Dialysis Fund", ["medicine", "chronic-care"], "chronic care", "adults", "Chennai", 3, 360_000,
     "Dialysis sessions for 25 low-income patients at a charitable centre in Chennai, India."),
    ("Environment", "Mongolia Winter Fodder Banks", ["climate", "herders"], "climate adaptation", "families", "Arkhangai", 3, 240_000,
     "Fodder banks so herding families in Arkhangai, Mongolia, keep their animals alive through extreme winters."),
    ("Health", "Caracas Children's Insulin Fund", ["medicine", "rare-disease"], "chronic care", "children", "Caracas", 4, 400_000,
     "Insulin, test strips and clinic visits for 40 children with type 1 diabetes in Caracas, Venezuela."),
    ("Water", "Guatemala Highland Water Filters", ["water", "health"], "clean water", "families", "Quiché", 3, 180_000,
     "Ceramic water filters for 250 Mayan families in Quiché, Guatemala, made by a local workshop."),
    ("Environment", "Atacama Fog Catchers", ["water", "climate"], "water storage", "community", "Chañaral", 2, 150_000,
     "Fog-catching nets that collect drinking and garden water for a coastal village near Chañaral, Chile."),
    ("Health", "Haiti Prosthetic Limbs Workshop", ["disability", "rehabilitation"], "rehabilitation", "adults", "Les Cayes", 4, 270_000,
     "Fitting 30 prosthetic legs and training a local technician in Les Cayes, Haiti."),
    ("Environment", "Honduras Coffee Farm Agroforestry", ["trees", "climate"], "land restoration", "families", "Copán", 2, 150_000,
     "Shade trees and soil care for 80 small coffee farms hit by rust and drought in Copán, Honduras."),
    ("Water", "Bolivia Altiplano Rain Ponds", ["water", "climate"], "water storage", "community", "Oruro", 3, 200_000,
     "Lined rain ponds for llama herders and potato farmers on the Altiplano near Oruro, Bolivia."),
    ("Health", "Colombia Border Migrant Clinic", ["medicine", "refugees"], "primary care", "families", "Cúcuta", 4, 250_000,
     "Free consultations and medicines for migrant families arriving in Cúcuta, Colombia."),
    ("Environment", "Galápagos Plastic-Free Beaches", ["recycling", "waste", "wildlife"], "waste", "community", "Puerto Ayora", 2, 110_000,
     "Beach cleanups and a refill station network to cut single-use plastic in Puerto Ayora, Ecuador."),
    ("Health", "Navajo Nation Elder Food Boxes", ["nutrition", "elderly-care"], "nutrition", "elderly", "Chinle", 3, 180_000,
     "Monthly healthy food boxes delivered to isolated elders around Chinle, Navajo Nation, USA."),
    ("Water", "Flint Home Water Filter Checks", ["water", "health"], "clean water", "families", "Flint", 3, 120_000,
     "Home visits to install and replace water filters for 300 households in Flint, Michigan, USA."),
    ("Health", "Lesbos Refugee Winter Kits", ["refugees", "emergency"], "emergency care", "families", "Lesbos", 4, 220_000,
     "Winter clothing, blankets and hygiene kits for 500 people in reception centres on Lesbos, Greece."),
    ("Health", "Kherson Generator for a Village Clinic", ["medicine", "emergency", "infrastructure"], "primary care", "community", "Kherson", 5, 210_000,
     "A generator and fuel so a village clinic near Kherson, Ukraine, keeps vaccines cold through blackouts."),
    ("Environment", "Romania Roma Settlement Clean Water", ["water", "infrastructure"], "clean water", "community", "Cluj", 3, 240_000,
     "Connecting a Roma settlement on the edge of Cluj-Napoca, Romania, to safe tap water."),
    ("Environment", "Scottish Highlands Peatland Repair", ["soil", "climate"], "conservation", "community", "Sutherland", 2, 180_000,
     "Blocking drainage ditches to re-wet damaged peat bogs with a crofting township in Sutherland, Scotland."),
    ("Health", "Faith Community Food Pantry, Detroit", ["faith-based", "nutrition"], "nutrition", "families", "Detroit", 3, 160_000,
     "A church-run food pantry adding fresh produce for 200 families a week in Detroit, USA."),
    ("Health", "Mosque-Run Night Shelter Clinic, Paris", ["faith-based", "medicine"], "primary care", "adults", "Paris", 3, 130_000,
     "Evening nurse consultations at a mosque-run night shelter in northern Paris, France."),
]

# Who runs each project on the ground (filled in only where a project has none).
FACILITATORS = {
    "Lanet Library": "Lanet Community Library Group",
    "Kaptembwo Desks": "Kaptembwo Primary Parents Association",
    "Girls' STEM Club": "Kisumu STEM Futures Network",
    "New Reading Corner": "Eldoret Early Readers Trust",
    "Mobile Eye Clinic": "Turkana Clear Sight Outreach",
    "St. Mary's Mission Maternity Ward": "St. Mary's Mission Health Committee",
    "Lupus Patient Support Fund": "Nairobi Lupus Support Network",
    "Lake Shoreline Trees": "Lakeside Youth Conservation Group",
    "Plastic-Free Market": "Kongowea Traders Welfare Group",
    "Village Borehole Repair": "Lokichar Village Water Committee",
    "School Rainwater Tanks": "Eldoret Schools Water Project",
    "Dhaka Household Water Filters": "Mirpur Clean Water Collective",
    "Lima Community Dental Van": "Sonrisas Lima Dental Outreach",
    "Manila Bay Mangrove Replanting": "Manila Bay Fisherfolk Alliance",
    "Gaza Field Clinic Medical Supplies": "Gaza Community Health Volunteers",
    "Gaza Household Water Deliveries": "Deir al-Balah Water Committee",
    "Adré Child Nutrition Centre": "Adré Mothers' Nutrition Network",
    "Sana'a Neighbourhood Water Filters": "Old City Clean Water Circle",
    "Port-au-Prince Cholera Prevention": "Cité Soleil Health Brigade",
    "Kharkiv Mobile Physiotherapy": "Kharkiv Rehab Friends",
    "Sindh Flood-Safe Hand Pumps": "Dadu Village Water Alliance",
    "Oaxaca Rainwater Harvesting": "Mixteca School Water Project",
    "Amazon Riverbank Reforestation": "Pará Riverside Growers Cooperative",
    "Lagos Lagoon Plastic Cleanup": "Makoko Waterfront Youth Collective",
    "Fiji Coral Reef Restoration": "Suva Reef Guardians",
    "Kathmandu Valley Clean Cookstoves": "Valley Clean Air Network",
    "Gaza Children's Trauma Counselling": "Khan Younis Child Wellbeing Team",
    "Gaza Dialysis Patient Transport": "Central Gaza Patient Transport Group",
    "West Bank Village Cisterns": "Hebron Hills Cistern Committee",
    "Beirut Elderly Home Visits": "Beirut Neighbours Care Circle",
    "Idlib Mobile Maternity Unit": "Northwest Syria Midwives Network",
    "Mosul Water Network Repair": "West Mosul Residents' Water Group",
    "Amman Rooftop Gardens": "Jabal Amman Growers",
    "Atlas Mountains Terrace Rebuilding": "Al Haouz Terrace Cooperative",
    "Taiz Cholera Treatment Corner": "Taiz District Health Volunteers",
    "Kabul Midwife Training": "Kabul Community Midwives Circle",
    "Goma Displacement Camp Clinic": "Kivu Lake Health Partners",
    "Tigray Spring Protection": "Tigray Highland Water Users",
    "Mogadishu Child Vaccination Days": "Banadir Child Health Network",
    "Sahel Great Green Wall Plots": "Tillabéri Farmers' Union",
    "Turkana Solar Water Kiosk": "Lodwar Water Kiosk Committee",
    "Kibera Sickle Cell Clinic Day": "Kibera Sickle Cell Parents",
    "Lake Victoria Water Hyacinth Removal": "Dunga Beach Fisherfolk Group",
    "Freetown Maternal Blood Bank": "Freetown Safe Births Volunteers",
    "Malawi Flood-Proof Boreholes": "Chikwawa Water Point Committees",
    "Madagascar Mangrove Nurseries": "Mahajanga Coastal Villages",
    "Kampala Disability Wheelchair Workshop": "Kampala Mobility Makers",
    "Juba School Handwashing Stations": "Juba Schools Hygiene Club",
    "Cox's Bazar Camp Eye Care": "Teknaf Sight Volunteers",
    "Sylhet Arsenic-Safe Wells": "Sylhet Safe Water Volunteers",
    "Sundarbans Embankment Planting": "Satkhira Embankment Guardians",
    "Rakhine Mobile Health Boat": "Sittwe River Health Team",
    "Mekong Delta Salt-Free Water Tanks": "Ben Tre Farmers' Water Group",
    "Borneo Orangutan Corridor Replanting": "Kinabatangan Village Restorers",
    "Mindanao Typhoon Clinic Rebuild": "Surigao Barangay Health Workers",
    "Tuvalu Coastal Seawall Plants": "Funafuti Shoreline Keepers",
    "Papua New Guinea Village Birth Kits": "Highlands Safe Motherhood Group",
    "Ladakh Ice Stupa Water Storage": "Leh Village Ice Builders",
    "Chennai Street Dialysis Fund": "Chennai Kidney Care Friends",
    "Mongolia Winter Fodder Banks": "Arkhangai Herders' Cooperative",
    "Caracas Children's Insulin Fund": "Caracas Diabetic Families Network",
    "Guatemala Highland Water Filters": "Quiché Filter Makers",
    "Atacama Fog Catchers": "Chañaral Fog Water Group",
    "Haiti Prosthetic Limbs Workshop": "Les Cayes Mobility Workshop",
    "Honduras Coffee Farm Agroforestry": "Copán Smallholder Coffee Group",
    "Bolivia Altiplano Rain Ponds": "Oruro Altiplano Water Users",
    "Colombia Border Migrant Clinic": "Cúcuta Border Health Volunteers",
    "Galápagos Plastic-Free Beaches": "Santa Cruz Island Youth",
    "Navajo Nation Elder Food Boxes": "Chinle Elders Support Circle",
    "Flint Home Water Filter Checks": "Flint Neighbourhood Water Watch",
    "Lesbos Refugee Winter Kits": "Lesbos Winter Volunteers",
    "Kherson Generator for a Village Clinic": "Kherson Village Clinic Friends",
    "Romania Roma Settlement Clean Water": "Pata Rât Residents' Association",
    "Scottish Highlands Peatland Repair": "Sutherland Crofters' Peat Group",
    "Faith Community Food Pantry, Detroit": "Eastside Congregations Pantry",
    "Mosque-Run Night Shelter Clinic, Paris": "Goutte d'Or Night Shelter Volunteers",
}

# The worked example's backers: (project, people, cents each), one seeded person per gift. Half the design's
# 25 / 25 / 100 so every gift is within the 50 USD per-person cap; the scores keep the design's 6000:1800:1200.
BACKERS = [("Lanet Library", 16, 1250), ("Kaptembwo Desks", 9, 1250), ("Girls' STEM Club", 4, 5000)]
SEED_BACKER = "Seed backer"

# project: [(title, cents, due in days from today, status)], in order; each project's tranches add up to its goal.
# Released tranches stay within what the seeded backers gave.
OPEN, EVIDENCE, HELD, RELEASED = (MilestoneStatus.open, MilestoneStatus.evidence_submitted,
                                  MilestoneStatus.held, MilestoneStatus.released)
MILESTONES = {
    "Lanet Library": [("Buy 40 books", 3000, 7, OPEN), ("Shelves for three schools", 197_000, 30, OPEN),
                      ("Librarian, first term", 200_000, 60, OPEN), ("300 more books", 200_000, 90, OPEN)],
    "Kaptembwo Desks": [("First 10 desks delivered", 10_000, -25, RELEASED), ("Next 15 desks", 150_000, -3, HELD),
                        ("Final 15 desks", 240_000, 40, OPEN)],
    "Girls' STEM Club": [("Science kits for 30 girls", 15_000, -30, RELEASED), ("Two coding laptops", 120_000, -2, EVIDENCE),
                         ("Mentor stipend, term one", 90_000, 35, OPEN), ("End-of-year science fair", 75_000, 80, OPEN)],
    "New Reading Corner": [("Mats and shelves", 50_000, 14, OPEN), ("150 picture books", 70_000, 40, OPEN),
                           ("Storytime volunteer training", 30_000, 70, OPEN)],
    "Mobile Eye Clinic": [("Screening kit and trial lenses", 150_000, 21, OPEN), ("First two village visits", 150_000, 50, OPEN),
                          ("Reading glasses for 400 people", 200_000, 85, OPEN)],
    "St. Mary's Mission Maternity Ward": [("Two delivery beds", 180_000, 25, OPEN), ("Solar fridge for vaccines", 270_000, 60, OPEN)],
    "Lupus Patient Support Fund": [("First quarter of medicine", 300_000, 20, OPEN), ("Clinic transport for 25 people", 200_000, 45, OPEN),
                                   ("Second quarter of medicine", 300_000, 110, OPEN)],
    "Lake Shoreline Trees": [("Seedlings and nursery beds", 150_000, 18, OPEN), ("Plant the first 1,000 trees", 200_000, 50, OPEN),
                             ("Plant 1,000 more and fence them", 150_000, 95, OPEN)],
    "Plastic-Free Market": [("Four collection points", 100_000, 15, OPEN), ("2,000 reusable bags", 100_000, 40, OPEN),
                            ("Trader workshops", 50_000, 70, OPEN)],
    "Village Borehole Repair": [("New pump and parts", 200_000, 10, OPEN), ("Install and test the water", 100_000, 30, OPEN),
                                ("Train two local mechanics", 50_000, 60, OPEN)],
    "School Rainwater Tanks": [("First 10,000-litre tank", 90_000, 20, OPEN), ("Second tank", 90_000, 45, OPEN),
                               ("Gutters and taps", 20_000, 60, OPEN)],
    "Dhaka Household Water Filters": [("First 60 filters", 150_000, 25, OPEN), ("Last 60 filters and training", 150_000, 55, OPEN)],
    "Lima Community Dental Van": [("Van fit-out", 200_000, 30, OPEN), ("Six months of visits", 200_000, 90, OPEN)],
    "Manila Bay Mangrove Replanting": [("Nursery and first 1,500 seedlings", 175_000, 30, OPEN),
                                       ("Last 1,500 seedlings", 175_000, 75, OPEN)],
    "Gaza Field Clinic Medical Supplies": [("First month of wound-care kits", 200_000, 10, OPEN), ("Antibiotics and insulin stock", 250_000, 35, OPEN), ("Second month of supplies", 150_000, 70, OPEN)],
    "Gaza Household Water Deliveries": [("Jerrycans for 400 families", 120_000, 7, OPEN), ("First month of water deliveries", 180_000, 30, OPEN), ("Second month of water deliveries", 150_000, 60, OPEN)],
    "Adré Child Nutrition Centre": [("Screening scales and MUAC tapes", 80_000, 14, OPEN), ("Three months of therapeutic food", 270_000, 45, OPEN), ("Community health worker stipends", 150_000, 90, OPEN)],
    "Sana'a Neighbourhood Water Filters": [("First 100 filters", 110_000, 20, OPEN), ("Last 100 filters", 110_000, 50, OPEN), ("Hygiene training sessions", 30_000, 70, OPEN)],
    "Port-au-Prince Cholera Prevention": [("Three rehydration points", 120_000, 15, OPEN), ("Six months of chlorine tablets", 120_000, 45, OPEN), ("Volunteer health promoters", 60_000, 80, OPEN)],
    "Kharkiv Mobile Physiotherapy": [("Van fit-out and equipment", 200_000, 25, OPEN), ("First three months of visits", 150_000, 60, OPEN), ("Mobility aids for 40 patients", 100_000, 95, OPEN)],
    "Sindh Flood-Safe Hand Pumps": [("First four pumps", 170_000, 30, OPEN), ("Last four pumps", 150_000, 65, OPEN), ("Pump caretaker training", 30_000, 80, OPEN)],
    "Oaxaca Rainwater Harvesting": [("Tanks for three schools", 130_000, 25, OPEN), ("Tanks for two schools", 70_000, 55, OPEN), ("Filters and maintenance kits", 20_000, 75, OPEN)],
    "Amazon Riverbank Reforestation": [("Tree nursery and seedlings", 150_000, 30, OPEN), ("Plant the first 2,500 trees", 130_000, 70, OPEN), ("Plant 2,500 more trees", 120_000, 120, OPEN)],
    "Lagos Lagoon Plastic Cleanup": [("Boats, nets and safety gear", 100_000, 20, OPEN), ("Plastic buy-back point", 120_000, 50, OPEN), ("Six months of cleanups", 60_000, 100, OPEN)],
    "Fiji Coral Reef Restoration": [("Coral nursery frames", 120_000, 30, OPEN), ("Replant the first reef patch", 120_000, 75, OPEN), ("Village reef monitoring", 80_000, 110, OPEN)],
    "Kathmandu Valley Clean Cookstoves": [("First 150 cookstoves", 120_000, 20, OPEN), ("Last 150 cookstoves", 100_000, 50, OPEN), ("Household follow-up visits", 20_000, 75, OPEN)],
    "Gaza Children's Trauma Counselling": [("Train 12 counsellors", 90_000, 14, OPEN), ("Three months of sessions", 160_000, 50, OPEN), ("Play kits for shelters", 50_000, 80, OPEN)],
    "Gaza Dialysis Patient Transport": [("First month of transport", 120_000, 10, OPEN), ("Second month of transport", 120_000, 40, OPEN), ("Third month of transport", 120_000, 70, OPEN)],
    "West Bank Village Cisterns": [("Repair the first 20 cisterns", 110_000, 30, OPEN), ("Repair 40 more cisterns", 190_000, 75, OPEN)],
    "Beirut Elderly Home Visits": [("Nurse visits, first quarter", 120_000, 30, OPEN), ("Medicines for a year", 130_000, 60, OPEN), ("Nurse visits, second quarter", 120_000, 120, OPEN)],
    "Idlib Mobile Maternity Unit": [("Equip the mobile unit", 220_000, 20, OPEN), ("Six months of midwife shifts", 260_000, 80, OPEN)],
    "Mosul Water Network Repair": [("Pipes and fittings", 200_000, 25, OPEN), ("Repair crews", 150_000, 55, OPEN), ("Water quality testing", 50_000, 75, OPEN)],
    "Amman Rooftop Gardens": [("Planters and drip kits", 90_000, 30, OPEN), ("Seeds and training", 40_000, 60, OPEN)],
    "Atlas Mountains Terrace Rebuilding": [("Stone and tools", 100_000, 30, OPEN), ("Rebuild 40 terraces", 150_000, 80, OPEN), ("500 almond saplings", 50_000, 110, OPEN)],
    "Taiz Cholera Treatment Corner": [("Beds and rehydration supplies", 140_000, 10, OPEN), ("Two months of staff", 120_000, 45, OPEN)],
    "Kabul Midwife Training": [("Course and trainers", 150_000, 30, OPEN), ("200 delivery kits", 100_000, 60, OPEN), ("Field mentoring", 80_000, 100, OPEN)],
    "Goma Displacement Camp Clinic": [("First quarter of medicines", 180_000, 15, OPEN), ("Nurse salary for six months", 150_000, 60, OPEN), ("Malaria nets", 70_000, 40, OPEN)],
    "Tigray Spring Protection": [("Protect the first three springs", 130_000, 30, OPEN), ("Protect three more springs", 130_000, 70, OPEN)],
    "Mogadishu Child Vaccination Days": [("Cold boxes and transport", 90_000, 20, OPEN), ("Four vaccination days", 110_000, 60, OPEN)],
    "Sahel Great Green Wall Plots": [("Dig 1,000 half-moon basins", 120_000, 40, OPEN), ("Plant 3,000 trees", 140_000, 90, OPEN)],
    "Turkana Solar Water Kiosk": [("Solar pump and panels", 180_000, 30, OPEN), ("Treatment unit and kiosk", 140_000, 60, OPEN)],
    "Kibera Sickle Cell Clinic Day": [("Screening tests for 300 children", 90_000, 20, OPEN), ("A year of medicines", 110_000, 60, OPEN)],
    "Lake Victoria Water Hyacinth Removal": [("Boats and cutting tools", 80_000, 25, OPEN), ("Briquette press", 100_000, 55, OPEN)],
    "Freetown Maternal Blood Bank": [("Blood fridge and backup power", 160_000, 30, OPEN), ("Six donor drives", 80_000, 75, OPEN)],
    "Malawi Flood-Proof Boreholes": [("Drill two boreholes", 160_000, 35, OPEN), ("Drill two more boreholes", 160_000, 80, OPEN)],
    "Madagascar Mangrove Nurseries": [("Two nurseries", 70_000, 30, OPEN), ("Plant 10,000 propagules", 110_000, 90, OPEN)],
    "Kampala Disability Wheelchair Workshop": [("Tools and materials", 110_000, 30, OPEN), ("Build and fit 60 wheelchairs", 120_000, 80, OPEN)],
    "Juba School Handwashing Stations": [("Stations for six schools", 60_000, 20, OPEN), ("Stations for six more schools", 60_000, 45, OPEN), ("A year of soap", 20_000, 60, OPEN)],
    "Cox's Bazar Camp Eye Care": [("Screening camps", 80_000, 20, OPEN), ("60 cataract surgeries", 240_000, 70, OPEN)],
    "Sylhet Arsenic-Safe Wells": [("Test 500 wells", 50_000, 20, OPEN), ("Drill five deep wells", 200_000, 80, OPEN)],
    "Sundarbans Embankment Planting": [("Seedlings and labour", 100_000, 40, OPEN), ("Second planting season", 90_000, 120, OPEN)],
    "Rakhine Mobile Health Boat": [("Fit out the boat", 150_000, 25, OPEN), ("Six months of trips", 180_000, 80, OPEN)],
    "Mekong Delta Salt-Free Water Tanks": [("100 household tanks", 160_000, 30, OPEN), ("100 more tanks", 140_000, 90, OPEN)],
    "Borneo Orangutan Corridor Replanting": [("Tree nursery", 90_000, 30, OPEN), ("Plant 4,000 trees", 160_000, 100, OPEN)],
    "Mindanao Typhoon Clinic Rebuild": [("Roof and walls", 170_000, 40, OPEN), ("Equipment and medicines", 110_000, 75, OPEN)],
    "Tuvalu Coastal Seawall Plants": [("Plant nursery", 60_000, 30, OPEN), ("Plant 1 km of shoreline", 120_000, 90, OPEN)],
    "Papua New Guinea Village Birth Kits": [("1,000 clean birth kits", 70_000, 20, OPEN), ("Train 40 birth attendants", 90_000, 60, OPEN)],
    "Ladakh Ice Stupa Water Storage": [("Pipes and fittings", 80_000, 40, OPEN), ("Build three ice stupas", 70_000, 100, OPEN)],
    "Chennai Street Dialysis Fund": [("First 300 sessions", 180_000, 30, OPEN), ("Next 300 sessions", 180_000, 90, OPEN)],
    "Mongolia Winter Fodder Banks": [("Hay and storage shed", 140_000, 40, OPEN), ("Second winter's stock", 100_000, 120, OPEN)],
    "Caracas Children's Insulin Fund": [("Six months of insulin", 160_000, 15, OPEN), ("Test strips and meters", 80_000, 40, OPEN), ("Second six months", 160_000, 180, OPEN)],
    "Guatemala Highland Water Filters": [("First 125 filters", 90_000, 25, OPEN), ("Last 125 filters", 90_000, 60, OPEN)],
    "Atacama Fog Catchers": [("Ten fog nets", 90_000, 40, OPEN), ("Tanks and pipes", 60_000, 80, OPEN)],
    "Haiti Prosthetic Limbs Workshop": [("Workshop equipment", 120_000, 30, OPEN), ("30 prosthetic legs", 150_000, 90, OPEN)],
    "Honduras Coffee Farm Agroforestry": [("20,000 shade tree seedlings", 90_000, 30, OPEN), ("Farmer field schools", 60_000, 80, OPEN)],
    "Bolivia Altiplano Rain Ponds": [("Dig and line eight ponds", 160_000, 40, OPEN), ("Fencing and spillways", 40_000, 80, OPEN)],
    "Colombia Border Migrant Clinic": [("Three months of medicines", 130_000, 15, OPEN), ("Doctor sessions", 120_000, 60, OPEN)],
    "Galápagos Plastic-Free Beaches": [("Refill stations", 70_000, 30, OPEN), ("Monthly beach cleanups", 40_000, 90, OPEN)],
    "Navajo Nation Elder Food Boxes": [("First three months of boxes", 90_000, 20, OPEN), ("Next three months", 90_000, 110, OPEN)],
    "Flint Home Water Filter Checks": [("Filters and cartridges", 80_000, 20, OPEN), ("Home visit volunteers", 40_000, 60, OPEN)],
    "Lesbos Refugee Winter Kits": [("500 winter kits", 150_000, 15, OPEN), ("Blankets and sleeping bags", 70_000, 30, OPEN)],
    "Kherson Generator for a Village Clinic": [("Generator and wiring", 120_000, 10, OPEN), ("Six months of fuel", 90_000, 60, OPEN)],
    "Romania Roma Settlement Clean Water": [("Pipe connection", 180_000, 40, OPEN), ("Six public taps", 60_000, 80, OPEN)],
    "Scottish Highlands Peatland Repair": [("Survey and dams", 90_000, 40, OPEN), ("Re-wet 20 hectares", 90_000, 120, OPEN)],
    "Faith Community Food Pantry, Detroit": [("Fridges and shelving", 70_000, 20, OPEN), ("Three months of produce", 90_000, 60, OPEN)],
    "Mosque-Run Night Shelter Clinic, Paris": [("Nurse sessions, first quarter", 80_000, 20, OPEN), ("Medicines and supplies", 50_000, 50, OPEN)],
}
EVIDENCE_URL = "https://files.example.com/seed/milestone-{id}-{kind}.jpg"
SEED_PAYEE = "seed-payee@example.com"


def seed_milestones(db: Session, project: Project, today: date) -> None:
    """Adds the project's missing milestones; an existing one only gets a due date if it has none."""
    for seq, (title, cents, due_in, status) in enumerate(MILESTONES.get(project.title, []), start=1):
        due = today + timedelta(days=due_in)
        milestone = db.scalar(select(Milestone).where(Milestone.project_id == project.id, Milestone.seq == seq))
        if milestone is not None:
            milestone.due_date = milestone.due_date or due
            continue
        milestone = Milestone(project_id=project.id, seq=seq, title=title, amount=cents, currency="USD",
                              due_date=due, status=status)
        db.add(milestone)
        db.flush()
        if status == OPEN:
            continue

        kinds = [DocumentKind.receipt, DocumentKind.photo] if status == RELEASED else [DocumentKind.receipt]
        for kind in kinds:
            db.add(ProjectDocument(project_id=project.id, milestone_id=milestone.id, kind=kind,
                                   file_url=EVIDENCE_URL.format(id=milestone.id, kind=kind.value)))
        if status == HELD:
            audit.write(
                db,
                actor="milestone-agent",
                action="payout_request",
                inputs={"milestone_id": milestone.id, "amount_cents": cents},
                rule_result="held_for_admin",
                reason=f"Held: above_threshold ({cents} > 50000). Summary: delivery note for 15 desks matches the receipt.",
            )
        if status == RELEASED:
            released_at = datetime.combine(due, datetime.min.time(), timezone.utc)
            db.add(LedgerEntry(type=LedgerType.tranche, amount=cents, currency="USD", project_id=project.id,
                               created_at=released_at))
            db.add(Payout(
                sender_batch_id=f"seed-milestone-{milestone.id}-USD", currency="USD", status=PayoutStatus.processing,
                paypal_batch_id=f"SEED-{milestone.id}", created_at=released_at,
                items=[{"project_id": project.id, "milestone_id": milestone.id, "amount_cents": cents,
                        "receiver": SEED_PAYEE, "status": "PENDING", "sender_item_id": f"milestone-{milestone.id}"}],
            ))


def main() -> None:
    create_schema(engine)  # also adds columns new since Render last deployed
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        categories = {}
        for name in ("Health", "Education", "Environment", "Water"):
            categories[name] = db.scalar(select(Category).where(Category.name == name)) or Category(name=name)
            db.add(categories[name])
        db.flush()

        for category, title, tags, cause, group, region, urgency, goal, summary in PROJECTS:
            project = db.scalar(select(Project).where(Project.title == title))
            if project is None:
                project = Project(
                    title=title, currency="USD", status=ProjectStatus.active,
                    verified_by="seed", verified_at=now,
                )
                db.add(project)
            project.category_id = categories[category].id
            project.tags, project.cause, project.beneficiary_group = tags, cause, group
            project.region, project.urgency, project.goal_amount = region, urgency, goal
            project.summary = project.summary or summary
            project.facilitator = project.facilitator or FACILITATORS[title]
        db.flush()

        for project in db.scalars(select(Project).where(Project.title.in_(list(MILESTONES)))):
            seed_milestones(db, project, now.date())

        round_ = db.scalar(select(Round).where(Round.status == RoundStatus.open))
        if round_ is None:
            round_ = Round(
                name="Dev round", starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=10),
                matching_pool=1_000_000, currency="USD", status=RoundStatus.open,
            )
            db.add(round_)
        round_.project_cap_pct = 40.0

        demo = db.scalar(select(Donor).order_by(Donor.id))
        if demo is None:
            demo = Donor(display_name="Demo donor", show_on_leaderboard=True)
            db.add(demo)

        if not db.scalar(select(Donor).where(Donor.display_name.like(f"{SEED_BACKER} %"))):
            n = 0
            for title, people, cents in BACKERS:
                project = db.scalar(select(Project).where(Project.title == title))
                for _ in range(people):
                    n += 1
                    backer = Donor(display_name=f"{SEED_BACKER} {n}")
                    db.add(backer)
                    db.flush()
                    db.add(Donation(
                        donor_id=backer.id, target_type=TargetType.PROJECT, project_id=project.id,
                        amount=cents, currency="USD", status=DonationStatus.captured, captured_at=now,
                    ))
        db.commit()

        for p in db.scalars(select(Project).order_by(Project.category_id, Project.id)):
            print(f"project {p.id}: {p.title} [{next(c for c, v in categories.items() if v.id == p.category_id)}]")
        print(f"round {round_.id}: {round_.name}, cap {round_.project_cap_pct}%, pool {round_.matching_pool} cents")
        print(f"demo donor: id {demo.id}")


if __name__ == "__main__":
    main()
