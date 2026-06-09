NVCC := nvcc
ARCH := sm_75
SRC_DIR := src
BIN_DIR := bin
INCLUDE := include

SRCS := $(wildcard $(SRC_DIR)/*.cu)
BINS := $(patsubst $(SRC_DIR)/%.cu,$(BIN_DIR)/%,$(SRCS))

.PHONY: all clean $(BINS)

all: $(BINS)

$(BIN_DIR)/%: $(SRC_DIR)/%.cu | $(BIN_DIR)
	$(NVCC) -arch=$(ARCH) -I$(INCLUDE) -o $@ $<

$(BIN_DIR):
	mkdir -p $(BIN_DIR)

# Targets directos: make 04 → compila y ejecuta 04_brute_force
%: $(SRC_DIR)/%.cu | $(BIN_DIR)
	$(NVCC) -arch=$(ARCH) -I$(INCLUDE) -o $(BIN_DIR)/$@ $<
	./$(BIN_DIR)/$@ $(ARGS)

clean:
	rm -rf $(BIN_DIR)
