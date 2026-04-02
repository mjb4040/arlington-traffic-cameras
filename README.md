# Arlington Traffic Cameras

A lightweight web application that displays Arlington County traffic camera locations on an interactive Google Map using public open data.

## Overview

This project takes a cleaned traffic camera dataset and renders it in a browser-based map application. The current version focuses on turning raw public data into a usable geospatial viewer with search, marker clustering, color-coded status markers, traffic overlay support, and camera detail popups.

The project was built as a practical exercise in:

- data cleanup and transformation
- client-side JavaScript development
- geospatial visualization
- Google Maps JavaScript API integration
- Google Cloud hosting
- Git and GitHub workflow

## Current Features

- Interactive Google map centered on Arlington, Virginia
- Camera markers plotted from cleaned JSON data
- Marker clustering for dense camera areas
- Color-coded markers by status:
  - green = online
  - red = offline
  - gray = unknown
- Search by camera name, site, status, or corridor text
- Polished info window for each camera
- Link from each camera popup to Google Maps
- Google traffic layer toggle
- Result count showing how many cameras are currently displayed

## Tech Stack

- HTML
- CSS
- JavaScript
- Google Maps JavaScript API
- Google Maps Marker Clusterer
- Python / Jupyter Notebook for data cleanup
- Google Cloud Storage for static hosting
- GitHub for version control
