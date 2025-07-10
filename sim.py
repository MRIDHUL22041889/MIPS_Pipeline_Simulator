# ---------------------- INSTRUCTION OBJECT ----------------------
class Instruction:
  def __init__(self, op, pc=None, rs=None, rt=None, rd=None, imm=None):
      self.op = op
      self.pc = pc
      self.rs = rs
      self.rt = rt
      self.rd = rd
      self.imm = imm
      self.stage = 'None'
      self.rs_val = None
      self.rt_val = None
      self.result = None

REG_NAME_MAP = {
    "0": "$zero", "1": "$at",
    "2": "$v0", "3": "$v1",
    "4": "$a0", "5": "$a1", "6": "$a2", "7": "$a3",
    "8": "$t0", "9": "$t1", "10": "$t2", "11": "$t3",
    "12": "$t4", "13": "$t5", "14": "$t6", "15": "$t7",
    "16": "$s0", "17": "$s1", "18": "$s2", "19": "$s3",
    "20": "$s4", "21": "$s5", "22": "$s6", "23": "$s7",
    "24": "$t8", "25": "$t9",
    "26": "$k0", "27": "$k1",
    "28": "$gp", "29": "$sp", "30": "$fp", "31": "$ra"
}
REG_NUM_MAP = {v: k for k, v in REG_NAME_MAP.items()}
# ---------------------- REGISTER FILE ----------------------
class RegisterFile:
  def __init__(self):
      self.reg = {str(i): 0 for i in range(32)}
      self.Lo=0
      self.Hi=0
      self.reg["0"] = 0

  def read(self, reg_num):
      if reg_num is None:
          return 0
      return self.reg.get(str(reg_num), 0)

  def write(self, reg_num, value):
      if reg_num is not None and str(reg_num) != "0":
          self.reg[str(reg_num)] = value
  def dump_registers(self):
    for i in range(32):
        reg_num = str(i)
        reg_name = REG_NAME_MAP.get(reg_num, f"${reg_num}")
        value = self.reg[reg_num] & 0xFFFFFFFF  # 2’s complement format
        print(f"{reg_name:>5}: 0x{value:08X}")
    print(f"   Hi: 0x{self.Hi & 0xFFFFFFFF:08X}")
    print(f"   Lo: 0x{self.Lo & 0xFFFFFFFF:08X}")



# ---------------------- DATA MEMORY ----------------------
class DataMemory:
  def __init__(self):
      self.memory = {}

  def load(self, address):
      return self.memory.get(address, 0)

  def store(self, address, value):
      self.memory[address] = value


# ---------------------- INSTRUCTION MEMORY ----------------------
class InstructionMemory:
  def __init__(self):
      self.instructions = []
      self.label_dict = {}

  def assemble(self, instr_strings):
      pc = 0
      for line in instr_strings:
          line = line.strip()
          if ':' in line:
              label, rest = line.split(':', 1)
              self.label_dict[label.strip()] = pc
              line = rest.strip()
              if not line:
                  continue
          if not line:
              continue

          parts = line.replace(',', '').split()
          opcode = parts[0]
          instr = Instruction(op=opcode, pc=pc)

          if opcode in ["addi", "andi", "ori", "slti","srl","sll","sra"]:
              instr.rt = instr.rd= parts[1].replace('$', '')  # destination for I-type
              instr.rs = parts[2].replace('$', '')  # source
              imm_str = parts[3]
              instr.imm = int(imm_str, 0)  # auto-detects 0x for hex
          elif opcode in ["lw", "sw"]:
            instr.rt = parts[1].replace('$', '')
            offset_base = parts[2]
            if '(' in offset_base and ')' in offset_base:
                offset, base = offset_base.split('(')
                base = base.replace(')', '').replace('$', '')
                instr.rs = base
                instr.imm = int(offset, 0)
            else:
                raise ValueError(f"Invalid memory operand: {offset_base}")


          elif opcode in ["mfhi","mflo"]:
              instr.rd = parts[1].replace('$', '')
              instr.imm = 0

          elif opcode in ["beq", "bne","blt","bgt","ble","bge"]:
              instr.rs = parts[1].replace('$', '')
              instr.rt = parts[2].replace('$', '')
              instr.imm = parts[3]  # label

          elif opcode in ["and", "or", "add", "sub", "slt","nor","mult"]:
              instr.rd = parts[1].replace('$', '')  # destination for R-type
              instr.rs = parts[2].replace('$', '')
              instr.rt = parts[3].replace('$', '')
          elif opcode in ["j","jal"]:
              instr.imm=parts[1]
          elif opcode in ["jr"]:
              instr.rs=parts[1].replace('$','')
          elif opcode in ["div"]:
              instr.rs=parts[1].replace('$','')
              instr.rt=parts[2].replace('$','')
          elif opcode == "nop":
              pass  # No registers for nop

          self.instructions.append(instr)
          pc += 4

      return self.instructions, self.label_dict


# ---------------------- FORWARDING FUNCTIONS ----------------------
def check_fwd(ex_mem_rd, ex_mem_regwrite, mem_wb_rd, mem_wb_regwrite, if_id_rs, if_id_rt):
  """Check if forwarding is needed for RS and RT"""
  fwd_src_rs = "00"  # No forwarding
  fwd_src_rt = "00"  # No forwarding

  # Forwarding for RS
  if ex_mem_regwrite and ex_mem_rd is not None and ex_mem_rd != "0" and ex_mem_rd == if_id_rs:
      fwd_src_rs = "10"  # Forward from EX/MEM
  elif mem_wb_regwrite and mem_wb_rd is not None and mem_wb_rd != "0" and mem_wb_rd == if_id_rs:
      fwd_src_rs = "01"  # Forward from MEM/WB

  # Forwarding for RT
  if ex_mem_regwrite and ex_mem_rd is not None and ex_mem_rd != "0" and ex_mem_rd == if_id_rt:
      fwd_src_rt = "10"  # Forward from EX/MEM
  elif mem_wb_regwrite and mem_wb_rd is not None and mem_wb_rd != "0" and mem_wb_rd == if_id_rt:
      fwd_src_rt = "01"  # Forward from MEM/WB

  return fwd_src_rs, fwd_src_rt


def check_load_stall(id_ex_memread, id_ex_rt, if_id_rs, if_id_rt):
  """Check if a load-use stall is needed"""
  if id_ex_memread and id_ex_rt and (id_ex_rt == if_id_rs or id_ex_rt == if_id_rt):
      return True  # Stall needed
  else:
      return False  # No stall


# ---------------------- STAGES ----------------------
def IF(pc, imem):
  if pc < len(imem.instructions) * 4:
      instr = imem.instructions[pc // 4]
      instr.stage = "IF"
      branch_stall=0
      global total_instr
      total_instr += 1
      if instr.op in ["beq","bne","bgt","blt","ble","bge","j","jal","jr"]:
          branch_stall=1
          global b_instr
          b_instr += 1
      return instr,branch_stall
  return None,None

def ID(instr, rf, label_dict, pc, ex_mem_regwrite, ex_mem_rd, mem_wb_rd, ex_mem_instr, mem_wb_regwrite, mem_wb_instr, id_ex_instr):
    branch_taken = False
    new_pc = None

    if not instr or instr.op is None:
        return instr, branch_taken, new_pc


    op = instr.op
    imm = instr.imm

    rs_val = rf.read(instr.rs) if instr.rs else 0
    rt_val = rf.read(instr.rt) if instr.rt else 0



    # ------------------ FIX 1: Forward from ID/EX (EX stage) ------------------
    if id_ex_instr and id_ex_instr.op in ["addi", "add", "sub", "and", "or", "slt", "nor", "lw", "srl", "sll", "sra", "andi", "ori", "slti", "mfhi", "mflo"]:
        id_ex_rd = id_ex_instr.rd if id_ex_instr.rd else id_ex_instr.rt
        if id_ex_rd and id_ex_rd != "0":
            if id_ex_rd == instr.rs:
                rs_val = id_ex_instr.result
            if id_ex_rd == instr.rt:
                rt_val = id_ex_instr.result

    # ------------------ Existing Forwarding from EX/MEM ------------------
    if ex_mem_regwrite and ex_mem_rd and ex_mem_rd != "0":
        if ex_mem_rd == instr.rs:
            rs_val = ex_mem_instr.result
        if ex_mem_rd == instr.rt:
            rt_val = ex_mem_instr.result

    # ------------------ Existing Forwarding from MEM/WB ------------------
    if mem_wb_regwrite and mem_wb_rd and mem_wb_rd != "0":
        if mem_wb_rd == instr.rs:
            rs_val = mem_wb_instr.result
        if mem_wb_rd == instr.rt:
            rt_val = mem_wb_instr.result


    instr.rs_val = rs_val
    instr.rt_val = rt_val

    print("[DEBUG]:", rs_val, rt_val)

    # Branch decision
    if op == "beq" and rs_val == rt_val:
        branch_taken = True
    elif op == "bne" and rs_val != rt_val:
        branch_taken = True
    elif op == "blt" and rs_val < rt_val:
        branch_taken = True
    elif op == "bgt" and rs_val > rt_val:
        branch_taken = True
    elif op == "ble" and rs_val <= rt_val:
        branch_taken = True
    elif op == "bge" and rs_val >= rt_val:
        branch_taken = True
    elif op in ["j", "jal", "jr"]:
        branch_taken = True
        if op == "jal":
            rf.write(31, instr.pc + 4)

    if branch_taken:
        if op == "jr":
            new_pc = rs_val
        elif imm in label_dict:
            new_pc = label_dict[imm]

    return instr, branch_taken, new_pc

def EX(instr, rf, label_dict, fwd_rs, fwd_rt, fwd_enabled=True, ex_mem_instr=None, mem_wb_instr=None):
    if instr:
        instr.stage = "EX"
        op = instr.op

        # Get base register values
        rs_val = getattr(instr, 'rs_val', 0)
        rt_val = getattr(instr, 'rt_val', 0)

        # Apply forwarding for RS
        if fwd_enabled:
            if fwd_rs == "10" and ex_mem_instr and hasattr(ex_mem_instr, 'result'):
                rs_val = ex_mem_instr.result
                instr.rs_val = rs_val
                print(f"    [FWD] RS forwarded from EX/MEM: {rs_val}")
            elif fwd_rs == "01" and mem_wb_instr and hasattr(mem_wb_instr, 'result'):
                rs_val = mem_wb_instr.result
                instr.rs_val = rs_val
                print(f"    [FWD] RS forwarded from MEM/WB: {rs_val}")

            # Apply forwarding for RT
            if fwd_rt == "10" and ex_mem_instr and hasattr(ex_mem_instr, 'result'):
                rt_val = ex_mem_instr.result
                instr.rt_val = rt_val
                print(f"    [FWD] RT forwarded from EX/MEM: {rt_val}")
            elif fwd_rt == "01" and mem_wb_instr and hasattr(mem_wb_instr, 'result'):
                rt_val = mem_wb_instr.result
                instr.rt_val = rt_val
                print(f"    [FWD] RT forwarded from MEM/WB: {rt_val}")

        # Special handling for SW: ensure the stored value is also correct
        if op == "sw":
            instr.rt_val = rt_val  # Forwarded value or original

        imm = instr.imm

        # ALU and other computations
        if op in ["add", "sub", "and", "or", "slt", "nor"]:
            instr.result = {
                "add": rs_val + rt_val,
                "sub": rs_val - rt_val,
                "and": rs_val & rt_val,
                "or": rs_val | rt_val,
                "nor": ~(rs_val | rt_val),
                "slt": 1 if rs_val < rt_val else 0
            }[op]
        elif op == "mult":
            rf.Lo = (rs_val * rt_val) & 0xFFFFFFFF
            rf.Hi = (rs_val * rt_val) >> 32
            instr.result = rf.Lo
        elif op == "div":
            if rt_val != 0:
                rf.Lo = rs_val // rt_val
                rf.Hi = rs_val % rt_val
                instr.result = rf.Lo
            else:
                instr.result = 0
                print("Exception: divide by zero")
        elif op in ["mfhi"]:
            instr.result = rf.Hi
        elif op in ["mflo"]:
            instr.result = rf.Lo
        elif op in ["lw", "sw"]:
            instr.result = rs_val + imm
        elif op in ["addi", "andi", "ori", "slti"]:
            instr.result = {
                "addi": rs_val + imm,
                "andi": rs_val & imm,
                "ori": rs_val | imm,
                "slti": 1 if rs_val < imm else 0
            }[op]
        elif op in ["srl", "sll", "sra"]:
            if rs_val < 0:
                print("SHAMT must be positive")
            else:
                if op == "srl":
                    instr.result = (rs_val % 0x100000000) >> imm
                elif op == "sll":
                    instr.result = rs_val << imm
                elif op == "sra":
                    instr.result = rs_val >> imm

    return instr


def MEM(instr, dmem):
    if instr:
        instr.stage = "MEM"
        if instr.op == "lw":
            instr.result = dmem.load(instr.result)  # Loaded value replaces the computed address
            print(f"[MEM] LW: Loaded {instr.result} from address")
        elif instr.op == "sw":
            dmem.store(instr.result, instr.rt_val)
            print(f"[MEM] SW: Storing value {instr.rt_val} to address {instr.result}")
    return instr


def WB(instr, rf):
    if instr:
        instr.stage = "WB"
        op = instr.op
        if op in ["add", "sub", "and", "or", "slt", "nor", "mult", "div", "mfhi", "mflo"]:
            if instr.rd:
                rf.write(instr.rd, instr.result)
                print(f"    [WB] Writing ${instr.rd} = {instr.result}")
        elif op in ["addi", "andi", "ori", "slti", "lw", "srl", "sll", "sra"]:
            if instr.rt:
                rf.write(instr.rt, instr.result)
                print(f"    [WB] Writing ${instr.rt} = {instr.result}")




# ---------------------- SIMULATE ----------------------
STAGES = ["IF", "ID", "EX", "MEM", "WB"]
def get_dest_reg(instr):
    if instr.op in ["add", "sub", "and", "or", "slt", "nor", "mult", "div", "mfhi", "mflo"]:
        return instr.rd
    elif instr.op in ["addi", "andi", "ori", "slti", "lw", "srl", "sll", "sra"]:
        return instr.rt
    else:
        return None

def simulate(imem, rf, dmem):
    pc = 0
    cycle = -1
    pipeline = {stage: None for stage in STAGES}
    instructions = imem.instructions
    label_dict = imem.label_dict
    stall_next_if = False
    instr_completed = 0
    control_stalls = 0

    while (pc < len(instructions) * 4 or any(pipeline.values())) and cycle < 20:
        cycle += 1
        print(f"Cycle {cycle:02d} | Pipeline: {{ IF: {pipeline['IF'].op if pipeline['IF'] else 'None'}, "
      f"ID: {pipeline['ID'].op if pipeline['ID'] else 'None'}, "
      f"EX: {pipeline['EX'].op if pipeline['EX'] else 'None'}, "
      f"MEM: {pipeline['MEM'].op if pipeline['MEM'] else 'None'}, "
      f"WB: {pipeline['WB'].op if pipeline['WB'] else 'None'} }}")


        ex_mem_instr = pipeline["MEM"]
        mem_wb_instr = pipeline["WB"]
        id_ex_instr = pipeline["EX"]

        ex_mem_instrID = pipeline["EX"]
        mem_wb_instrID = pipeline["MEM"]
        id_ex_instrID = pipeline["ID"]

        WRITEBACK_OPS = ["add", "sub", "and", "or", "slt", "nor", "mult", "div", 
                         "mfhi", "mflo", "addi", "andi", "ori", "slti", "lw", 
                         "srl", "sll", "sra"]

        ex_mem_rd, ex_mem_regwrite = None, False
        if ex_mem_instr and ex_mem_instr.op in WRITEBACK_OPS:
            ex_mem_rd = get_dest_reg(ex_mem_instr)
            ex_mem_regwrite = ex_mem_rd is not None

        mem_wb_rd, mem_wb_regwrite = None, False
        if mem_wb_instr and mem_wb_instr.op in WRITEBACK_OPS:
            mem_wb_rd = get_dest_reg(mem_wb_instr)
            mem_wb_regwrite = mem_wb_rd is not None

        ex_mem_rdID, ex_mem_regwriteID = None, False
        if ex_mem_instrID and ex_mem_instrID.op in WRITEBACK_OPS:
            ex_mem_rdID = get_dest_reg(ex_mem_instrID)
            ex_mem_regwriteID = ex_mem_rdID is not None

        mem_wb_rdID, mem_wb_regwriteID = None, False
        if mem_wb_instrID and mem_wb_instrID.op in WRITEBACK_OPS:
            mem_wb_rdID = get_dest_reg(mem_wb_instrID)
            mem_wb_regwriteID = mem_wb_rdID is not None

        fwd_rs, fwd_rt = "00", "00"
        if id_ex_instr:
            fwd_rs, fwd_rt = check_fwd(ex_mem_rd, ex_mem_regwrite, mem_wb_rd, mem_wb_regwrite, id_ex_instr.rs, id_ex_instr.rt)

        if pipeline["WB"]:
            WB(pipeline["WB"], rf)
            instr_completed += 1

        pipeline["WB"] = MEM(pipeline["MEM"], dmem) if pipeline["MEM"] else None

        pipeline["MEM"] = EX(pipeline["EX"], rf, label_dict, fwd_rs, fwd_rt, True, ex_mem_instr, mem_wb_instr) if pipeline["EX"] else None

        load_stall = False

        # Load-use hazard check for lw in EX
        if pipeline["EX"] and pipeline["EX"].op == "lw" and pipeline["ID"]:
            lw_rt = pipeline["EX"].rt
            id_rs = pipeline["ID"].rs
            id_rt = pipeline["ID"].rt
            if lw_rt and (lw_rt == id_rs or lw_rt == id_rt):
                load_stall = True

        # Load-use hazard check for lw in MEM (lw result not yet available)
        if pipeline["MEM"] and pipeline["MEM"].op == "lw" and pipeline["ID"]:
            lw_rt = pipeline["MEM"].rt
            id_rs = pipeline["ID"].rs
            id_rt = pipeline["ID"].rt
            if lw_rt and (lw_rt == id_rs or lw_rt == id_rt):
                load_stall = True

        if load_stall:
            pipeline["EX"] = None
            stall_next_if = True
            control_stalls += 1
            continue  # Stall the pipeline

        pipeline["EX"] = pipeline["ID"]

        branch_taken, new_pc = False, None
        if pipeline["EX"]:
            pipeline["EX"], branch_taken, new_pc = ID(
    pipeline["EX"], rf, label_dict, pc,
    ex_mem_regwriteID, ex_mem_rdID, mem_wb_rdID,
    ex_mem_instrID, mem_wb_regwriteID, mem_wb_instrID,
    pipeline["EX"]  # <-- Pass ID/EX stage instr here
)  # This is the fixed call

            if branch_taken and new_pc is not None:
                pc = new_pc

        pipeline["ID"] = pipeline["IF"]

        if stall_next_if:
            pipeline["IF"] = None
            stall_next_if = False
            control_stalls += 1
        else:
            if pc < len(instructions) * 4:
                fetched_instr, branch_stall = IF(pc, imem)
                pipeline["IF"] = fetched_instr
                if fetched_instr:
                    pc += 4
                if branch_stall:
                    stall_next_if = True
                    control_stalls += 1
            else:
                pipeline["IF"] = None

    return cycle, instr_completed

# ---------------------- MAIN PROGRAM ----------------------
imem = InstructionMemory()
rf = RegisterFile()
dmem = DataMemory()

program = """
addi $t0, $zero, 8       # $t0 = 8
addi $t1, $zero, 15      # $t1 = 15
sw   $t1, 0($t0)         # Mem[8] = 15
lw   $t2, 0($t0)         # $t2 = Mem[8]
bne  $t2, $zero, next    # Taken
addi $t3, $zero, 1       # skipped
next:
addi $t3, $zero, 2       # $t3 = 2


"""

instr_list = program.strip().split('\n')
instructions, labels = imem.assemble(instr_list)

print("Labels:", labels)
print("\nInstructions:")
for instr in instructions:
  print(f"PC 0x{instr.pc:08X}: {instr.op} (rs={instr.rs}, rt={instr.rt}, rd={instr.rd}, imm={instr.imm})")
print("\n" + "="*60)
print("PIPELINE SIMULATION")
print("="*60)
total_instr = 0
b_instr = 0
PIPELINE_DEPTH = 5
cycle_count, instr_completed = simulate(imem, rf, dmem)

# Correct stall calculation accounts for pipeline drain
total_stalls = max(0, cycle_count - (instr_completed + PIPELINE_DEPTH - 1))

cpi = cycle_count / instr_completed if instr_completed else 0

print(f"\nTotal Cycles: {cycle_count}")
print(f"Total Instructions: {instr_completed}")
print(f"Total Stalls: {total_stalls}")
print(f"CPI: {cpi:.2f}\n")

print("Final Register Values:")
for reg, val in rf.reg.items():
    if val != 0:
        reg_name = REG_NAME_MAP.get(reg, f"${reg}")
        print(f"{reg_name:>5}: 0x{(val & 0xFFFFFFFF):08X}")
print("\nMemory Contents:")
for addr, val in sorted(dmem.memory.items()):
    print(f"Mem[{addr}] = {val}")
