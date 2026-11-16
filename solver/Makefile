# ECE 3340 Circuit Solver Project
#
#   make         build the solver (library PLU, or yours: see USE_MY_PLU in main.cpp)
#   make clean   remove the built program
#
# Windows (MinGW / MSYS2): same commands; the program is solver.exe.

CXX      ?= g++
CXXFLAGS ?= -O2 -std=c++11 -Wall -Wextra
CXXFLAGS += -I../lib

# Your file. (Instructor: "make REF=1" builds with the reference solution.)
ifdef REF
PLU_SRC = ../instructor/plu_reference.cpp
CXXFLAGS += -I.
else
PLU_SRC = plu_student.cpp
endif

SRC     = main.cpp netlist.cpp mna.cpp plu_library.cpp $(PLU_SRC)
HEADERS = netlist.h mna.h plu.h

solver: $(SRC) $(HEADERS)
	$(CXX) $(CXXFLAGS) -o $@ $(SRC)

clean:
	rm -f solver solver.exe

.PHONY: clean
