# Offender-Employment-Search
A tool written in Python (3.12.12) that allows registered sex offenders to find employment and housing by calculating distance from prohibited zones.


# Disclaimer

⚠️ Always double-check a company or residence's location before accepting a job or signing a lease.  
Use this tool at your own risk. The author is **not responsible for civil, legal, or other consequences** that may arise from its use.


## Support Development

If you like this tool, consider supporting development:

- [PayPal](https://paypal.me/collinjfox)


## How to use
-Download FindSafeLocations.py
 

-Obtain a Google Cloud "Google Places" API Key (Free for up to 10000 requests, each use of this program will perform 10-1000 Google Places requests)


-Install Python (project was written in 3.12.12) 


-Set your API_KEY value near top of FindSafeLocations.py


-Uncomment (remove the three double-quote symbols) from function "fetch_shelby_county_boundary()" and include your county's FIPS code


-From a command prompt:

"python FindSafeLocations.py"


-Replace the shelby_polygon value with the value for your county's polygon that gets printed to the screen


-comment out function "fetch_shelby_county_boundary()"


-Run the program again


-Follow the on-screen prompts