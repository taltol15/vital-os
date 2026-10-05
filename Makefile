.PHONY: iso check screenshots host-deps clean

iso:
	sudo ./build.sh iso

check:
	./build.sh check

screenshots:
	./build.sh screenshots

host-deps:
	sudo ./build.sh install-deps

clean:
	sudo ./build.sh clean
