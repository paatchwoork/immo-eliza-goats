import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import json
import csv
import asyncio
import aiohttp
from time import perf_counter
import time
import pandas as pd



class ImmoCrawler():
    def __init__(self) -> None:
        self.base_url = "https://www.immoweb.be/en/search/house-and-apartment/for-sale?countries=BE&isALifeAnnuitySale=false&orderBy=postal_code&page="
        self.links = []
        self.property_data = {}
        self.property_key = 0
        self.links_counter = 0
        

    async def crawl_page(self, session, page, semaphore):
        async with semaphore:

            try:
                async with session.get(f"{self.base_url}{page}") as response:
                    response.raise_for_status()
                    html = await response.text()
                    r = BeautifulSoup(html, "html.parser")
                    properties = r.find_all("a", attrs={"class": "card__title-link"})
                    self.page_counter = len(properties) * page
                    for property in properties:
                            href = property.get("href")
                            if "new-real-estate-project-apartments" in href or "new-real-estate-project-houses" in href:
                                async with session.get(f"{href}") as response:
                                    html = await response.text()
                                    r = BeautifulSoup(html, "html.parser")
                                    sub_properties = r.find_all("a", attrs={"class":"classified__list-item-link"})
                                
                                    for sub_property in sub_properties:
                                        self.links_counter += 1
                                        self.links.append(sub_property.get("href"))
                                        
                                        self.property_key += 1
                                        print(f"Grabbing Links & Extracting Data: {self.property_key}/{len(self.links)}")
                                        self.get_data(session, sub_property.get("href"))

                            else:
                                self.links_counter += 1
                                
                                self.links.append(property.get("href"))
                                self.property_key += 1
                                print(f"Grabbing Links & Extracting Data: {self.property_key}/{len(self.links)}")
                                await self.get_data(session, property.get("href"))
                    
            except Exception as error:
                print(f"Error in thread for page {page}: {error}")


    async def get_data(self, session, url):
        try:
            async with session.get(url) as response:
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                scripts = soup.find_all("script", attrs={"type": "text/javascript"})
                #print(script)

                for script in scripts:
                    if "window.classified" in script.get_text():
                        classified_script = script
                        break
                
                
                # Extract the text content of the script tag
                script_content = classified_script.get_text()

                # Use string manipulation to extract the window.classified object
                json_str = script_content[script_content.find('{'):script_content.rfind('}') + 1]

                # Load the JSON data
                data = json.loads(json_str)
                
                def multi_get(dict_obj, *attrs, default=None):
                    result = dict_obj
                    for attr in attrs:
                        if not result or attr not in result:
                            return default
                        result = result[attr]
                    return result
                
                if data is not None:
                
                    #self.property_data[self.property_key] = defaultdict(None)
                    self.property_data[self.property_key] = {
                        "link": url,
                        "id": data.get('id',None),
                        "locality": multi_get(data,'property','location','district'),
                        "zip_code":multi_get(data,'property','location','postalCode'),
                        "price": multi_get(data,'transaction','sale','price'),
                        "property_type": multi_get(data,'property','type'),
                        "subproperty_type": multi_get(data,'property','subtype'),
                        "bedroom_count": multi_get(data,'property','bedroomCount'),
                        "total_area_m2": multi_get(data,'property','netHabitableSurface'),
                        "equipped_kitchen": 1 if multi_get(data,'property','kitchen','type') else 0,
                        "furnished": 1 if multi_get(data,'transaction','sale','isFurnished') else 0,
                        "open_fire": 1 if multi_get(data, 'property', 'fireplaceExists') else 0,
                        "terrace": multi_get(data,'property','terraceSurface') if data['property']['hasTerrace'] else 0,
                        "garden": multi_get(data,'property','gardenSurface') if data['property']['hasGarden'] else 0,
                        "surface_land": multi_get(data,'property','land','surface'),
                        "swimming_pool": 1 if multi_get(data,'property','hasSwimmingPool') else 0,
                        "state_building": multi_get(data,'property','building','condition'),
                        "public_sales":  multi_get(data,'flag','isPublicSale'), 
                        "notary_sales":  multi_get(data,'flag','isNotarySale'),
                        }
                    
                
                    

            
            
            return self.property_data[self.property_key]
        except Exception as error:
            print(f"Error in gathering data from {url}: {error}") 

    async def get_properties(self, num_pages=333):
        start_time = perf_counter()
        
        semaphore = asyncio.Semaphore(15)  # Adjust the semaphore count based on server limits

        async with aiohttp.ClientSession() as session:
            tasks = [self.crawl_page(session, page, semaphore) for page in range(1, num_pages + 1)]
            await asyncio.gather(*tasks)
            

    
    def to_csv(self, name):
        df = pd.DataFrame.from_dict(self.property_data, orient='index')
        df.to_csv(name + '.csv')
