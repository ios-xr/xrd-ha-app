chart_dir () {
    readlink -f "${BATS_TEST_DIRNAME}/../.."
}

release_name () {
    echo -n "release-name"
}
