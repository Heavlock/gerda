#!/usr/bin/env bash
set -euo pipefail

runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/herdr-dictation"
output_dir="$runtime_dir/output"
pid_file="$runtime_dir/record.pid"
pane_file="$runtime_dir/pane"
audio_file="$runtime_dir/prompt.wav"
record_log="$runtime_dir/record.log"
transcribe_log="$runtime_dir/transcribe.log"
assistant_lock="$runtime_dir/assistant.lock"

gerda_root="@ROOT@"
models_root="$gerda_root/models"
gigaam_model_dir="$models_root/gigaam-v3-e2e-rnnt"
gerda_python="$gerda_root/.venv/bin/python"
herdr_bin="${HERDR_BIN_PATH:-$HOME/.local/bin/herdr}"

notify() {
    notify-send -a Herdr "Диктовка" "$1" >/dev/null 2>&1 || true
}

fail() {
    notify "$1"
    exit 1
}

recording_pid() {
    [[ -r "$pid_file" ]] || return 1

    local pid cmdline
    IFS= read -r pid <"$pid_file"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/$pid/cmdline" ]] || return 1

    cmdline="$(tr '\0' ' ' <"/proc/$pid/cmdline")"
    [[ "$cmdline" == *"pw-record"* && "$cmdline" == *"$audio_file"* ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1

    printf '%s' "$pid"
}

cleanup_prompt_files() {
    rm -f \
        "$audio_file" \
        "$pane_file" \
        "$record_log" \
        "$output_dir/prompt.txt" \
        "$output_dir/prompt.srt" \
        "$output_dir/prompt.json"
}

mkdir -p "$output_dir"
exec 9>"$runtime_dir/lock"
if ! flock -n 9; then
    notify "Предыдущая операция ещё выполняется"
    exit 0
fi

if pid="$(recording_pid)"; then
    kill -INT "$pid" 2>/dev/null || true

    for _ in {1..100}; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.05
    done

    if kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null || true
        for _ in {1..40}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.05
        done
    fi

    if kill -0 "$pid" 2>/dev/null; then
        fail "Не удалось остановить запись"
    fi

    exec 8>>"$assistant_lock"
    if ! flock -w 2 8; then
        fail "Не удалось заблокировать активацию Герды"
    fi

    rm -f "$pid_file"
    notify "Распознаю речь…"

    [[ -s "$audio_file" ]] || fail "Запись не содержит аудио"
    [[ -r "$pane_file" ]] || fail "Не сохранена панель назначения"
    IFS= read -r target_pane <"$pane_file"
    [[ -n "$target_pane" ]] || fail "Не сохранена панель назначения"

    rm -f \
        "$output_dir/prompt.txt" \
        "$output_dir/prompt.srt" \
        "$output_dir/prompt.json" \
        "$transcribe_log"

    [[ -e "$gigaam_model_dir/v3_e2e_rnnt_encoder.int8.onnx" ]] || fail "Не найдена локальная модель GigaAM"
    transcribe_command=(
        env PYTHONPATH="$gerda_root"
        "$gerda_python" -m assistant.russian_dictation prompt
    )

    if ! "${transcribe_command[@]}" >"$output_dir/prompt.txt" 2>"$transcribe_log"; then
        rm -f "$audio_file" "$output_dir/prompt.txt"
        fail "Ошибка распознавания; журнал: $transcribe_log"
    fi

    [[ -r "$output_dir/prompt.txt" ]] || fail "Распознавание не создало текстовый результат"
    text="$(tr '\n' ' ' <"$output_dir/prompt.txt" | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//')"

    if [[ -z "$text" ]]; then
        cleanup_prompt_files
        rm -f "$transcribe_log"
        notify "Речь не распознана"
        exit 0
    fi

    if ! "$herdr_bin" pane send-text "$target_pane" "$text" >>"$transcribe_log" 2>&1; then
        rm -f "$audio_file"
        fail "Не удалось вставить текст в панель $target_pane"
    fi

    cleanup_prompt_files
    rm -f "$transcribe_log"
    notify "Текст вставлен в Codex — проверьте и нажмите Enter"
    exit 0
fi

rm -f "$pid_file"
target_pane="${HERDR_ACTIVE_PANE_ID:-${HERDR_PANE_ID:-}}"
[[ -n "$target_pane" ]] || fail "Herdr не передал активную панель"

[[ -x "$gerda_python" && -r "$gerda_root/assistant/russian_daemon.py" ]] || fail "Не установлено окружение распознавания Герды"
[[ -e "$gigaam_model_dir/v3_e2e_rnnt_encoder.int8.onnx" ]] || fail "Не найдена локальная модель GigaAM"

exec 8>>"$assistant_lock"
if ! flock -w 1 8; then
    fail "Другая голосовая операция уже выполняется"
fi

cleanup_prompt_files
printf '%s\n' "$target_pane" >"$pane_file"

nohup pw-record \
    --rate 16000 \
    --channels 1 \
    --format s16 \
    "$audio_file" >"$record_log" 2>&1 </dev/null 9>&- 8>&8 &
pid=$!
printf '%s\n' "$pid" >"$pid_file"

sleep 0.25
if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file" "$pane_file" "$audio_file"
    fail "Не удалось начать запись; журнал: $record_log"
fi

# Start model loading while the microphone records; no worker runs at login.
systemctl --user --no-block start gerda-russian.service >/dev/null 2>&1 || true
notify "Запись началась — нажмите F8 для завершения"
