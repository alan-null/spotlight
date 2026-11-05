# Invocation history is separate from the shared action cache. No query hooks.
spotlight_history_ids=() spotlight_history_sources=()
spotlight_history_templates=() spotlight_history_values=() spotlight_history_records=()

spotlight_history_load() {
  spotlight_history_ids=() spotlight_history_sources=()
  spotlight_history_templates=() spotlight_history_values=() spotlight_history_records=()
  (( SPOTLIGHT_HISTORY_LIMIT > 0 )) || return 0
  [[ -f $SPOTLIGHT_HISTORY_FILE ]] || return 0
  local line id source template value extra
  while IFS= read -r line || [[ -n $line ]]; do
    IFS=$'\t' read -r id source template value extra <<< "$line"
    [[ $id == v:snippet:* || $id == v:module:* || $id == v:install-actions ]] || continue
    [[ $source == v:* && $template == v:* && $value == v:* && -z $extra ]] || continue
    decode_file_path "file:${id#v:}"; spotlight_history_ids+=("$REPLY")
    decode_file_path "file:${source#v:}"; spotlight_history_sources+=("$REPLY")
    decode_file_path "file:${template#v:}"; spotlight_history_templates+=("$REPLY")
    decode_file_path "file:${value#v:}"; spotlight_history_values+=("$REPLY")
    spotlight_history_records+=("$line")
    (( ${#spotlight_history_ids[@]} < SPOTLIGHT_HISTORY_LIMIT )) || break
  done < "$SPOTLIGHT_HISTORY_FILE"
}

spotlight_history_promote() {
  local index value preview hint
  {
    for index in "${!spotlight_history_records[@]}"; do
      value=${spotlight_history_values[index]}
      if [[ $value =~ [[:cntrl:]] ]]; then printf -v value '%q' "$value"; fi
      encode_file_path "$value"; preview=$REPLY
      encode_file_path "${value:0:160}"; hint=$REPLY
      printf '%s\tv:%s\tv:%s\n' "${spotlight_history_records[index]}" "$preview" "$hint"
    done
    printf '__SPOTLIGHT_CATALOG__\n%s\n' "$1"
  } | awk -v hint_color="$SPOTLIGHT_ANSI_HINT" -f "$MODULE_DIR/lib/history.awk"
}

spotlight_history_record() {
  (( SPOTLIGHT_HISTORY_LIMIT > 0 )) || return 0
  local LC_ALL=C value record='' separator=''
  for value in "$@"; do
    encode_file_path "$value"
    record+="${separator}v:$REPLY"
    separator=$'\t'
  done
  printf '%s\n' "$record" | python3 "$MODULE_DIR/lib/history.py" record "$SPOTLIGHT_HISTORY_LIMIT"
}
