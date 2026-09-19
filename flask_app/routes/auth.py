"""Compatibility redirects for the former server-rendered account pages."""
from flask import Blueprint, redirect

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.get("/login")
def login():
    return redirect("/login")

@auth_bp.get("/register")
def register():
    return redirect("/register")
