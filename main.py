"""
Simple RSS reader
"""
import os
import sys
import threading
import argparse
import shutil
from pathlib import Path
from urllib.parse import unquote
from collections import OrderedDict
from flask import (
   Flask,
   render_template_string,
   jsonify,
   request,
   send_from_directory,
   url_for,
   redirect,
   Response,
)
from flask import Flask, send_from_directory, abort, render_template_string, redirect, url_for


def get_project_version(pyproject_text):
    for line in pyproject_text.split("\n"):
        wh = line.find("version")
        if wh >= 0:
            sp = line.split("=")
            trimmed = sp[1].strip()
            return trimmed[1:-1]
    return "0.0.0"

def get_project_name(pyproject_text):
    for line in pyproject_text.split("\n"):
        wh = line.find("name")
        if wh >= 0:
            sp = line.split("=")
            trimmed = sp[1].strip()
            return trimmed[1:-1]


path = Path("pyproject.toml")
pyproject_text = path.read_text()
__version__ = get_project_version(pyproject_text)
__project_name__ = get_project_name(pyproject_text)



app = Flask(__name__)

# Hardcode your directory path here (absolute or relative)
#SHARED_DIR = os.path.abspath("./my_shared_files")
SHARED_DIR = os.path.abspath("/mnt/Public/Tytan/Muzyka/wszystkie")

# Ensure the directory exists on startup
if not os.path.exists(SHARED_DIR):
    os.makedirs(SHARED_DIR)
    print(f"Created directory at: {SHARED_DIR}")
else:
    print(f"Serving files from: {SHARED_DIR}")

# Clean, responsive HTML interface with modern styling (embedded for simplicity)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Browser</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 40px auto;
            max-width: 800px;
            background-color: #f4f6f8;
            color: #333;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        }
        h1 {
            font-size: 1.6rem;
            margin-top: 0;
            color: #2c3e50;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 12px;
        }
        .breadcrumb {
            margin-bottom: 20px;
            font-size: 0.95rem;
            color: #7f8c8d;
        }
        .breadcrumb a {
            color: #3498db;
            text-decoration: none;
        }
        .breadcrumb a:hover {
            text-decoration: underline;
        }
        ul {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        li {
            padding: 12px 15px;
            border-bottom: 1px solid #f1f1f1;
            display: flex;
            align-items: center;
            transition: background 0.15s ease;
        }
        li:last-child {
            border-bottom: none;
        }
        li:hover {
            background-color: #fcfcfc;
        }
        .icon {
            font-size: 1.3rem;
            margin-right: 12px;
            user-select: none;
        }
        .item-link {
            text-decoration: none;
            color: #2980b9;
            font-weight: 500;
            flex-grow: 1;
        }
        .item-link:hover {
            color: #3498db;
            text-decoration: underline;
        }
        .parent-dir {
            font-weight: bold;
            color: #7f8c8d;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📁 Network Storage Browser</h1>
        
        <!-- Breadcrumb navigation -->
        <div class="breadcrumb">
            <a href="{{ url_for('browse') }}">Root</a>
            {% if breadcrumbs %}
                {% set current_path = [] %}
                {% for part in breadcrumbs %}
                    {% set _ = current_path.append(part) %}
                    / <a href="{{ url_for('browse', req_path=current_path|join('/')) }}">{{ part }}</a>
                {% endfor %}
            {% endif %}
        </div>

        <ul>
            <!-- Back to parent option -->
            {% if show_back %}
            <li>
                <span class="icon">⬆️</span>
                <a href="{{ url_for('browse', req_path=parent_path) }}" class="item-link parent-dir">.. (Parent Directory)</a>
            </li>
            {% endif %}

            <!-- Directories list -->
            {% for dir in dirs %}
            <li>
                <span class="icon">📁</span>
                <a href="{{ url_for('browse', req_path=(req_path + '/' + dir) if req_path else dir) }}" class="item-link">{{ dir }}/</a>
            </li>
            {% endfor %}

            <!-- Files list -->
            {% for file in files %}
            <li>
                <span class="icon">📄</span>
                <!-- target="_blank" opens files in a new tab if supported by browser -->
                <a href="{{ url_for('serve_file', filename=(req_path + '/' + file) if req_path else file) }}" class="item-link" target="_blank">{{ file }}</a>
            </li>
            {% endfor %}
            
            {% if not dirs and not files %}
            <li style="color: #95a5a6; font-style: italic;">This directory is empty</li>
            {% endif %}
        </ul>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    # Automatically redirect from Root domain to the browser path
    return redirect(url_for('browse'))


@app.route('/browse', defaults={'req_path': ''})
@app.route('/browse/<path:req_path>')
def browse(req_path):
    # Resolve the requested directory relative to SHARED_DIR
    target_path = os.path.abspath(os.path.join(SHARED_DIR, req_path))

    # --- ENHANCED SECURITY CHECK ---
    # We find the relative path between target_path and SHARED_DIR.
    # If the relative path starts with '..', they're trying to escape SHARED_DIR.
    rel_path = os.path.relpath(target_path, SHARED_DIR)
    if rel_path.startswith('..') or rel_path.startswith('/'):
        abort(403, "Access Forbidden: Directory escape detected.")

    # Ensure path exists
    if not os.path.exists(target_path):
        abort(404, "Directory or file not found.")

    # If it is a file, redirect directly to the downloader
    if os.path.isfile(target_path):
        return redirect(url_for('serve_file', filename=req_path))

    # Get directory contents safely
    try:
        raw_items = os.listdir(target_path)
    except PermissionError:
        abort(403, "Permission Denied accessing this directory.")

    # Separate items into directories and files (ignoring hidden files)
    dirs = []
    files = []
    for item in raw_items:
        if item.startswith('.'):  # Hide hidden files like .DS_Store
            continue
        item_path = os.path.join(target_path, item)
        if os.path.isdir(item_path):
            dirs.append(item)
        else:
            files.append(item)

    # Sort files and folders alphabetically
    dirs.sort()
    files.sort()

    # Generate path segments for breadcrumbs navigation
    breadcrumbs = [p for p in req_path.split('/') if p] if req_path else []
    parent_path = "/".join(breadcrumbs[:-1]) if breadcrumbs else ""

    return render_template_string(
        HTML_TEMPLATE,
        req_path=req_path,
        dirs=dirs,
        files=files,
        breadcrumbs=breadcrumbs,
        show_back=len(breadcrumbs) > 0,
        parent_path=parent_path
    )


@app.route('/files/<path:filename>')
def serve_file(filename):
    """
    Serves standard files directly.
    """
    # Change as_attachment to True if you want browser downloads forced instantly
    # Set to False so the browser displays PDF/Images/Text directly if supported
    return send_from_directory(SHARED_DIR, filename, as_attachment=False)


if __name__ == '__main__':
    # Use host='0.0.0.0' to make it available to your local network
    app.run(host='0.0.0.0', port=8000, debug=True)
