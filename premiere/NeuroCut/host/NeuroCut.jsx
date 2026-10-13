/**
 * NeuroCut Premiere Pro host script (ExtendScript).
 * Applies precomputed timeline layout from the FastAPI plugin backend.
 */

var TICKS_PER_SECOND = 254016000000;

function browseMediaFile() {
    var file = File.openDialog("Select video file", "*.mp4;*.mov;*.mkv;*.avi;*.mxf;*.webm");
    if (file) {
        return file.fsName;
    }
    return "";
}

function secondsToTicks(seconds) {
    return Math.round(seconds * TICKS_PER_SECOND);
}

function normalizePath(pathValue) {
    if (!pathValue) {
        return "";
    }
    return String(pathValue).replace(/\\/g, "/");
}

function findImportedItem(bin, mediaPath) {
    var target = normalizePath(mediaPath).toLowerCase();
    for (var i = 0; i < bin.children.numItems; i++) {
        var item = bin.children[i];
        if (item.type === ProjectItemType.BIN) {
            var nested = findImportedItem(item, mediaPath);
            if (nested) {
                return nested;
            }
            continue;
        }
        if (item.getMediaPath) {
            var itemPath = normalizePath(item.getMediaPath()).toLowerCase();
            if (itemPath === target) {
                return item;
            }
        }
    }
    return null;
}

function ensureSequence(project, masterItem, sequenceName) {
    if (project.activeSequence) {
        return project.activeSequence;
    }

    if (masterItem.createNewSequenceFromClips) {
        masterItem.createNewSequenceFromClips(sequenceName, [masterItem]);
        if (project.activeSequence) {
            return project.activeSequence;
        }
    }

    throw new Error("Failed to create sequence in Premiere.");
}

function applyEditPlan(jsonStr) {
    var payload;

    try {
        payload = JSON.parse(jsonStr);
    } catch (parseError) {
        return JSON.stringify({ ok: false, error: "Invalid JSON payload" });
    }

    if (!payload.media_path) {
        return JSON.stringify({ ok: false, error: "media_path is required" });
    }

    if (!app.project) {
        return JSON.stringify({ ok: false, error: "Open a Premiere Pro project" });
    }

    app.enableQE();
    app.beginUndoGroup("NeuroCut AI Edit");

    try {
        var project = app.project;
        var mediaPath = payload.media_path;
        var clips = payload.timeline_clips || [];
        var markers = payload.timeline_markers || [];
        var sequenceName = "NeuroCut " + String(payload.job_id || "edit").substr(0, 8);

        var imported = project.importFiles([mediaPath], true, project.rootItem, false);
        if (!imported) {
            throw new Error("Failed to import media: " + mediaPath);
        }

        var masterItem = findImportedItem(project.rootItem, mediaPath);
        if (!masterItem) {
            throw new Error("Imported file not found in project");
        }

        var sequence = ensureSequence(project, masterItem, sequenceName);
        project.activeSequence = sequence;

        for (var i = 0; i < clips.length; i++) {
            var clip = clips[i];
            var trackIndex = Math.max(0, (clip.track || 1) - 1);
            var inTicks = secondsToTicks(clip.source_start_sec || 0);
            var outTicks = secondsToTicks(clip.source_end_sec || 0);

            if (outTicks <= inTicks) {
                continue;
            }

            var subClip = masterItem.createSubClip(
                clip.name || ("Clip " + (i + 1)),
                inTicks,
                outTicks,
                false,
                true,
                true
            );

            var insertTime = new Time();
            insertTime.seconds = clip.timeline_start_sec || 0;
            sequence.overwriteClip(subClip, insertTime, trackIndex, trackIndex);
        }

        for (var m = 0; m < markers.length; m++) {
            var markerData = markers[m];
            var marker = sequence.markers.createMarker(markerData.time_sec || 0);
            marker.name = markerData.name || ("Marker " + (m + 1));
            marker.comments = markerData.comment || "";
        }

        app.endUndoGroup();
        return JSON.stringify({ ok: true, sequence: sequence.name });
    } catch (error) {
        app.endUndoGroup();
        return JSON.stringify({ ok: false, error: String(error) });
    }
}
