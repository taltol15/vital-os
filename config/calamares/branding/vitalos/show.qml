import QtQuick 2.5

Rectangle {
    id: root
    color: "#0E1116"
    anchors.fill: parent

    Image {
        id: mark
        source: "logo.png"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -36
        width: 96
        height: 96
        fillMode: Image.PreserveAspectFit
    }

    Text {
        anchors.top: mark.bottom
        anchors.topMargin: 28
        anchors.horizontalCenter: parent.horizontalCenter
        text: "Installing Vital OS"
        color: "#F6F1E7"
        font.pixelSize: 28
        font.family: "Inter"
    }

    Text {
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 42
        anchors.horizontalCenter: parent.horizontalCenter
        text: "Version 0.1.0    Based on Ubuntu 24.04 LTS"
        color: "#C6A56A"
        font.pixelSize: 14
        font.family: "Inter"
    }
}
