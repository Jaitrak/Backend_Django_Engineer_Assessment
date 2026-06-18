# Fuel Route Optimizer

A high-performance Django REST Framework API that calculates optimal travel routes across the USA, identifies cost-effective fuel stops within a 500-mile vehicle range, and computes the total fuel cost.

---

## 🚀 Key Features

- **Greedy Viability Fuel Optimization**: Selects the cheapest viable fuel stops to complete the journey, avoiding unnecessary stops or "dead ends" where a vehicle would run out of fuel.
- **Offline Coordinate Lookups**: Geocodes more than 6,000 cities offline using a pre-compiled JSON database derived from SimpleMaps, ensuring extremely fast imports and zero external API hits during import.
- **Advanced Caching Strategy**: Integrates Django's `LocMemCache` to cache route coordinates (24-hour TTL) and geocoding responses (30-day TTL) using key normalization, minimizing latency and external API consumption.
- **Interactive Documentation**: Out-of-the-box Swagger UI and Redoc API documentation via `drf-spectacular`.
- **Robust Error Handling**: Standardized JSON error response schemas for geocoding, routing, and optimization failures.
- **Comprehensive Test Suite**: Full suite of unit and integration tests using `pytest`, covering import commands, cache, services, views, and optimization logic.

---

## 📋 Vehicle Assumptions

- **Maximum Range**: 500 miles on a full tank.
- **Fuel Efficiency**: 10 miles per gallon (MPG).
- **Refueling Policy**: The vehicle starts with a full tank.
- **Short Route Fallback**: For routes ≤ 500 miles, no fuel stops are made, and fuel cost is computed as `(distance / 10) * average_imported_fuel_price`.

---

## 🛠️ Local Development Setup

Follow these steps to set up the project on your local machine using a Python virtual environment.

### 1. Clone & Prepare Directory
Make sure you are in the project root directory:
```bash
cd [path_to_project] \ Backend_Django_Engineer_Assessment
```

### 2. Create Virtual Environment
```bash
python -m venv venv
```

### 3. Activate Virtual Environment
- **Windows (PowerShell)**:
  ```powershell
  venv\Scripts\Activate.ps1
  ```
- **Windows (CMD)**:
  ```cmd
  venv\Scripts\activate.bat
  ```
- **Linux/macOS**:
  ```bash
  source venv/bin/activate
  ```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Create a file named `.env` in the project root directory (`D:\Backend_Django_Engineer_Assessment\.env`) and add your OpenRouteService API key and other settings:
```env
DEBUG=True
SECRET_KEY=django-insecure-production-ready-key-change-this-in-prod-123
ALLOWED_HOSTS=127.0.0.1,localhost
ORS_API_KEY=your_openrouteservice_api_key_here
```
> [!IMPORTANT]
> To get a free API key, register at [OpenRouteService](https://openrouteservice.org/).

### 6. Run Database Migrations
```bash
python manage.py migrate
```

### 7. Import Fuel Prices Dataset
Run the custom management command to clean, deduplicate, geocode, and import the fuel price CSV dataset:
```bash
python manage.py import_truckstops fuel-prices-for-be-assessment_U.csv
```
Upon completion, the command prints import statistics similar to the following:
```text
Reading input file...
Found 8151 raw records. Processing...
Clearing existing database entries...
Inserting 6222 geocoded records...

--- Import Summary Statistics ---
Imported: 8151
Duplicates removed: 1413
Geocoded: 6222
Failed: 516
Average fuel price: $3.41
---------------------------------
```

---

## ⚡ Running the Application

Start the local Django development server:
```bash
python manage.py runserver
```
The application will be running at `http://127.0.0.1:8000/`.

---

## 📖 Interactive API Documentation

Interactive OpenAPI documentation is available via:
- **Swagger UI**: [http://127.0.0.1:8000/api/docs/swagger/](http://127.0.0.1:8000/api/docs/swagger/)
- **Redoc**: [http://127.0.0.1:8000/api/docs/redoc/](http://127.0.0.1:8000/api/docs/redoc/)
- **Raw OpenAPI Schema (JSON)**: [http://127.0.0.1:8000/api/schema/](http://127.0.0.1:8000/api/schema/)

---

## 📡 API Endpoints

### Route Optimization Endpoint

- **URL**: `/api/route/`
- **Method**: `POST`
- **Content-Type**: `application/json`

#### Request Payload
```json
{
  "start": "Houston, TX",
  "finish": "Miami, FL"
}
```

#### Successful Response (`200 OK`)
```json
{
  "route_geometry": {
    "type": "LineString",
    "coordinates": [
      [-95.3698, 29.7604],
      ...
      [-80.1918, 25.7617]
    ]
  },
  "total_distance_miles": 1187.35,
  "total_fuel_cost": 387.42,
  "fuel_stops": [
    {
      "truckstop_id": "70201",
      "name": "Love's Travel Speed",
      "address": "123 Main St",
      "city": "Defuniak Springs",
      "state": "FL",
      "retail_price": 3.259,
      "latitude": 30.7202,
      "longitude": -86.1158
    },
    {
      "truckstop_id": "70451",
      "name": "Pilot Travel Center",
      "address": "456 Loop Rd",
      "city": "Lake City",
      "state": "FL",
      "retail_price": 3.219,
      "latitude": 30.1897,
      "longitude": -82.6393
    }
  ]
}
```

#### Error Response (`400 Bad Request` / `500 Internal Server Error`)
The API uses a standardized error payload format:
```json
{
  "error": {
    "code": "geocoding_error",
    "message": "Start location: Location 'Invalid City' could not be resolved to coordinates."
  }
}
```
Possible error codes:
- `invalid_request`: Input validation failed (missing `start` or `finish`).
- `geocoding_error`: Start or finish address could not be resolved to coordinates.
- `route_not_found`: No drivable route exists between start and finish.
- `optimization_error`: The vehicle ran out of fuel range due to a station gap > 500 miles.
- `internal_error`: An unexpected server-side exception.

---

## 🧠 Architectural & Design Details

### 1. Offline Geocoding Mapping
To ensure fast database importing without external dependencies, we use a pre-geocoded lookup file located at [fuel/data/geocoded_cities.json](file:///D:/Backend_Django_Engineer_Assessment/fuel/data/geocoded_cities.json).
- During the data import command, cities and states are normalized (whitespace stripped, case-insensitive) and looked up in the JSON map.
- If a city is missing (mostly Canadian locations or remote areas), the import logs a warning and skips the record, maintaining data integrity for USA queries.

### 2. High-Performance Caching
Using Django's internal `LocMemCache`, caching is enforced to guarantee fast response times:
- **Geocoding Cache**: Key format `geocode:{sha256_hash_of_normalized_query}` (TTL: 30 days).
- **Routing Cache**: Key format `route:{sha256_hash_of_normalized_start_and_finish}` (TTL: 24 hours).
- **Key Normalization**: Location names are lowercased, punctuation is stripped, and multiple spaces are collapsed to prevent duplicate API hits for minor typing variations.
- **Backend-Safe Key Generation**: Key inputs are hashed using SHA-256 before querying the cache backend. This avoids spaces, colons, or control characters, eliminating `CacheKeyWarning` and ensuring compatibility with all production cache engines (such as Redis or Memcached).

### 3. Route Projection & Bounding Box Queries
To optimize the search space of truck stops:
- The service extracts the minimum and maximum latitudes/longitudes from the route coordinates, adding a `0.5°` buffer margin (approx. 35 miles).
- A single SQL query retrieves only the candidates inside this bounding box (utilizing database composite indexes on `latitude` and `longitude`).
- For the filtered candidate stops, we project them onto the route by calculating the minimum Haversine distance from the stop to the route coordinates.
- Only stops within a `50-mile` threshold of the route coordinates are considered.

### 4. Greedy Viability Search
For journeys exceeding 500 miles:
1. Calculates cumulative distances along the route coordinates.
2. Identifies all stops reachable from the current location (within a 500-mile driving range).
3. Evaluates if each reachable stop is "viable"—meaning the vehicle can either reach the final destination directly from it, or there is another truck stop further along within 500 miles.
4. Picks the **cheapest** viable stop in range, refuels, and updates the current position.
5. Continues until the destination is within 500 miles range.

### 5. Development-Only Configuration Choices
To keep the project lightweight and friendly for local review:
- **SQLite Database**: A local SQLite database is utilized, eliminating the need for a separate database server.
- **LocMemCache**: Django's built-in local memory caching backend is used instead of a external Redis or Memcached server, providing out-of-the-box caching without additional infrastructure overhead.
- **DEBUG Mode**: Defaulting to `True` for development so that stack traces and interactive API documentation are rendered correctly.
- **Allowed Hosts**: Defaulting to `["*"]` to allow smooth local hosting.

---

## ⚠️ Known Limitations
- **Geocoding Coverage**: The offline geocoding database contains coordinates for ~6,000 cities in the USA. Locations outside this dataset (including Canadian and international cities) cannot be resolved.
- **Single Bounding Box**: The route projection queries stations in a rectangular bounding box around the start and finish locations. If a route loops widely outside the bounding box, some stations might be omitted, although the 0.5-degree buffer mitigates this for standard routes.
- **Greedy Optimization**: The fuel optimizer uses a greedy search algorithm that picks the cheapest viable station at each step. While highly efficient ($O(N)$ running time), it may not produce the global mathematically optimal set of stops in all theoretical edge cases, though it guarantees viability (i.e., not running out of fuel).

---

## 📈 Performance Notes
- **O(N) Complexity**: The greedy optimizer executes in linear time relative to the number of stations along the route.
- **Minimized DB Hits**: Candidate stations are queried using database index scans on latitude/longitude within a single SQL bounding-box query.
- **Zero Import API Overhead**: The import process performs offline geocoding using the local JSON dataset, causing zero external API calls.

---

## 🧪 Testing

To run the unit and integration test suite, execute `pytest` in the virtual environment:
```bash
pytest
```
Expected output:
```text
======================= 19 passed in 2.14s ========================
```
Test categories covered:
- **Import Commands**: Parsing CSVs, cleaning headers, resolving duplicate prices, skipping unmapped cities.
- **Service Layer**: Normalization logic, Cache hits/misses, Geocoding mock responses, Routing distance conversions.
- **Optimization Layer**: Short-route fallbacks, greedy viability stop selections, cost calculations, gap detection.
- **Views & Serialization**: Request payload validations (including identical start and finish inputs), error handling code outputs, REST payload responses.
