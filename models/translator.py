from datetime import datetime, timezone

from services.firebase_service import get_db
from services.geo_service import geohash_prefixes, haversine_miles, validate_coordinates


class TranslatorModel:
    collection_name = "translators"
    private_collection_name = "interpreterPrivate"
    public_fields = {
        "bio",
        "credentials",
        "dialects",
        "displayName",
        "languages",
        "photoUrl",
        "rating",
        "ratingCount",
        "serviceLocation",
        "serviceOptions",
        "specialties",
        "verificationStatus",
        "yearsExperience",
    }

    @classmethod
    def all_public(cls):
        docs = get_db().collection(cls.collection_name).stream()
        return [cls.to_public(doc) for doc in docs if doc.to_dict().get("verificationStatus") == "verified"]

    @classmethod
    def get(cls, translator_id, public=True):
        document = get_db().collection(cls.collection_name).document(translator_id).get()
        if not document.exists:
            return None
        if public and document.to_dict().get("verificationStatus") != "verified":
            return None
        return cls.to_public(document) if public else {"id": document.id, **document.to_dict()}

    @classmethod
    def get_private(cls, translator_id):
        document = get_db().collection(cls.private_collection_name).document(translator_id).get()
        return {"id": document.id, **document.to_dict()} if document.exists else {"id": translator_id}

    @classmethod
    def search(cls, language=None, languages=None, dialect=None, specialty=None, available_now=False,
               minimum_rating=0, verified_only=False, service_mode="both", latitude=None,
               longitude=None, radius_miles=None, limit=100):
        requested_languages = [str(value).casefold() for value in (languages or []) if str(value).strip()]
        if language:
            requested_languages.append(str(language).casefold())
        requested_languages = set(requested_languages)
        dialect = (dialect or "").casefold()
        specialty = (specialty or "").casefold()
        service_mode = str(service_mode or "both").casefold()
        if service_mode not in {"nearby", "remote", "both"}:
            raise ValueError("Search mode must be nearby, remote, or both.")
        radius = None if radius_miles in (None, "", "anywhere") else float(radius_miles)
        if radius is not None and radius not in {5, 10, 25, 50, 100}:
            raise ValueError("Distance must be 5, 10, 25, 50, 100, or anywhere.")
        has_origin = latitude not in (None, "") and longitude not in (None, "")
        if has_origin:
            latitude, longitude = validate_coordinates(latitude, longitude)
        elif service_mode == "nearby" or radius is not None:
            raise ValueError("A location is required for a nearby search.")

        collection = get_db().collection(cls.collection_name)
        documents = []
        # Geographic requests use indexed geohash prefix ranges so they do not
        # download the entire interpreter collection. Remote profiles are read
        # from a bounded verified query and merged by id.
        if has_origin and radius is not None and service_mode in {"nearby", "both"}:
            seen = set()
            for prefix in geohash_prefixes(latitude, longitude, radius):
                query = (collection.where("verificationStatus", "==", "verified")
                         .where("serviceLocation.geohash", ">=", prefix)
                         .where("serviceLocation.geohash", "<=", prefix + "\uf8ff")
                         .limit(max(20, min(int(limit), 100))))
                for document in query.stream():
                    if document.id not in seen:
                        seen.add(document.id)
                        documents.append(document)
            if service_mode == "both":
                remote_query = (collection.where("verificationStatus", "==", "verified")
                                .limit(max(20, min(int(limit), 100))))
                for document in remote_query.stream():
                    if document.id not in seen:
                        seen.add(document.id)
                        documents.append(document)
        elif service_mode == "remote":
            documents = list(collection.where("verificationStatus", "==", "verified")
                             .limit(max(20, min(int(limit), 100))).stream())
        else:
            # Unlocated/anywhere browsing is still bounded and verified at the
            # query layer instead of scanning every interpreter document.
            documents = list(collection.where("verificationStatus", "==", "verified")
                             .limit(max(20, min(int(limit), 100))).stream())

        profiles = []
        for document in documents:
            data = document.to_dict()
            if data.get("verificationStatus") != "verified":
                continue
            profile_languages = {str(value).casefold() for value in data.get("languages", [])}
            if requested_languages and not requested_languages.issubset(profile_languages):
                continue
            if dialect and dialect not in [str(value).casefold() for value in data.get("dialects", [])]:
                continue
            if specialty and specialty not in [str(value).casefold() for value in data.get("specialties", [])]:
                continue
            if available_now and not data.get("availability", {}).get("availableNow"):
                continue
            if float(data.get("rating") or 0) < float(minimum_rating or 0):
                continue
            if verified_only and data.get("verificationStatus") != "verified":
                continue
            service_options = data.get("serviceOptions") or {}
            location = data.get("serviceLocation") or {}
            map_visible = bool(location.get("showOnMap"))
            distance = None
            if has_origin and map_visible and location.get("latitude") is not None and location.get("longitude") is not None:
                distance = haversine_miles(latitude, longitude, location["latitude"], location["longitude"])
            interpreter_radius = float(service_options.get("radiusMiles") or 25)
            effective_radius = interpreter_radius if radius is None else min(radius, interpreter_radius)
            nearby_match = bool(service_options.get("inPerson") and map_visible and distance is not None and distance <= effective_radius)
            # Profiles created before serviceOptions existed were remote-capable
            # in FiniSpeak, so preserve that behavior during migration.
            remote_match = bool(service_options.get("remote", True))
            if service_mode == "nearby" and not nearby_match:
                continue
            if service_mode == "remote" and not remote_match:
                continue
            if service_mode == "both" and has_origin and radius is not None and not (nearby_match or remote_match):
                continue
            profile = cls.to_public(document)
            if distance is not None:
                profile["distanceMiles"] = round(distance, 1)
            profile["matchType"] = "nearby" if nearby_match else "remote" if remote_match else "anywhere"
            profiles.append(profile)
        profiles.sort(key=lambda profile: (bool(profile.get("availability", {}).get("availableNow")), float(profile.get("rating") or 0), int(profile.get("ratingCount") or 0)), reverse=True)
        return profiles[:max(1, min(int(limit), 100))]

    @classmethod
    def pending_verification(cls):
        db = get_db()
        results = []
        for doc in db.collection(cls.collection_name).stream():
            data = doc.to_dict()
            if data.get("credentialStatus") != "submitted" or data.get("verificationStatus") == "verified":
                continue
            private = db.collection(cls.private_collection_name).document(doc.id).get()
            private_data = private.to_dict() if private.exists else {}
            # Legacy profiles stored credential document metadata on the public
            # document. Keep this fallback only until the migration is run.
            credential_documents = private_data.get("credentialDocuments", data.get("credentialDocuments", []))
            results.append({"id": doc.id, **data, "credentialDocuments": credential_documents})
        return results

    @classmethod
    def set_verification(cls, translator_id, status, reviewer_id, notes=""):
        if status not in {"verified", "rejected", "needs_changes"}:
            raise ValueError("Invalid verification status.")
        ref = get_db().collection(cls.collection_name).document(translator_id)
        if not ref.get().exists:
            return None
        credential_status = "approved" if status == "verified" else status
        ref.set({
            "verificationStatus": status,
            "credentialStatus": credential_status,
            "onboardingStatus": status,
            "verifiedBy": reviewer_id,
            "verifiedAt": datetime.now(timezone.utc),
        }, merge=True)
        get_db().collection(cls.private_collection_name).document(translator_id).set({
            "verificationNotes": notes,
            "verifiedBy": reviewer_id,
            "verifiedAt": datetime.now(timezone.utc),
        }, merge=True)
        return cls.get(translator_id, public=False)

    @classmethod
    def update_availability(cls, translator_id, availability):
        ref = get_db().collection(cls.collection_name).document(translator_id)
        if not ref.get().exists:
            return None
        ref.set({"availability": availability, "updatedAt": datetime.now(timezone.utc)}, merge=True)
        return cls.get(translator_id, public=False)

    @classmethod
    def to_public(cls, doc):
        data = doc.to_dict()
        profile = {key: data[key] for key in cls.public_fields if key in data}
        availability = data.get("availability", {})
        profile["availability"] = {
            "availableNow": bool(availability.get("availableNow", False)),
            "days": availability.get("days", []) if isinstance(availability.get("days", []), list) else [],
            "start": availability.get("start", ""),
            "end": availability.get("end", ""),
        }
        location = data.get("serviceLocation") or {}
        if location.get("showOnMap"):
            profile["serviceLocation"] = {
                key: location.get(key) for key in ("city", "state", "country", "latitude", "longitude", "geohash", "showOnMap")
            }
        else:
            profile.pop("serviceLocation", None)
        options = data.get("serviceOptions") or {}
        profile["serviceOptions"] = {
            "inPerson": bool(options.get("inPerson", False)),
            "remote": bool(options.get("remote", True)),
            "radiusMiles": int(options.get("radiusMiles") or 25),
        }
        visible_reviews = []
        try:
            for review in doc.reference.collection("reviews").stream():
                data = review.to_dict()
                if data.get("moderationStatus", "visible") == "visible":
                    visible_reviews.append({
                        "id": review.id,
                        "authorName": data.get("authorName") or "FiniSpeak customer",
                        "rating": data.get("rating"),
                        "text": data.get("text", ""),
                        "createdAt": data.get("createdAt"),
                    })
            visible_reviews.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
        except Exception:
            # Discovery should remain available if one profile has malformed
            # legacy review data.
            visible_reviews = []
        profile["recentReviews"] = visible_reviews[:5]
        profile["id"] = doc.id
        return profile
