# Index once in native awk rather than looping over every catalog row in Bash.
BEGIN { FS = "\t"; count = 0; hex = "0123456789ABCDEF"; reset = sprintf("%c[0m", 27) }

function decode(value, result, position, high, low) {
    value = substr(value, 3) # v: keeps empty logical fields nonempty in Bash.
    while ((position = index(value, "%"))) {
        result = result substr(value, 1, position - 1)
        high = index(hex, toupper(substr(value, position + 1, 1))) - 1
        low = index(hex, toupper(substr(value, position + 2, 1))) - 1
        if (high >= 0 && low >= 0 && length(value) >= position + 2) {
            result = result sprintf("%c", high * 16 + low)
            value = substr(value, position + 3)
        } else {
            result = result "%"
            value = substr(value, position + 1)
        }
    }
    return result value
}

!catalog && $0 == "__SPOTLIGHT_CATALOG__" { catalog = 1; next }
!catalog {
    id[count] = decode($1); source[count] = decode($2)
    template[count] = decode($3); resolved[count] = decode($4)
    preview[count] = decode($5); hint[count] = decode($6)
    count++
    next
}

NF >= 2 {
    rows[++total] = $0; row_id[total] = $2
    current[$2] = $0; title[$2] = $1; category[$2] = $3
    description[$2] = $4; command[$2] = $5; file[$2] = $6
}

END {
    for (i = 0; i < count; i++) {
        key = id[i]
        if (!(key in current)) continue
        display = title[key]
        sub(/^  /, "", display)
        display = "↺ " display
        if (key ~ /^snippet:/) {
            if (source[i] != file[key] || template[i] != command[key] || resolved[i] == "") continue
            if (template[i] == resolved[i]) omit[key] = 1
            else display = display "  " hint_color hint[i] reset
            printf "%s\trecent:%d:%s\t%s\t%s\t%s\t%s\n", display, i, key, category[key], description[key], preview[i], file[key]
        } else {
            rest = substr(current[key], index(current[key], "\t") + 1)
            printf "%s\trecent:%d:%s\n", display, i, rest
            omit[key] = 1
        }
    }
    for (i = 1; i <= total; i++) if (!(row_id[i] in omit)) print rows[i]
}
