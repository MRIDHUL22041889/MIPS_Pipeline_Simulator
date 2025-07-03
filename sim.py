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
              instr.rt = parts[1].replace('$', '')  # destination for I-type
              instr.rs = parts[2].replace('$', '')  # source
              imm_str = parts[3]
              instr.imm = int(imm_str, 0)  # auto-detects 0x for hex
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


def ID(instr, rf,label_dict,pc):
  branch_taken = False
  new_pc = None
  if instr:
      op = instr.op
      imm=instr.imm
      rs_val = getattr(instr, 'rs_val', 0)
      rt_val = getattr(instr, 'rt_val', 0)
      instr.rs_val = rf.read(instr.rs) if instr.rs else 0
      instr.rt_val = rf.read(instr.rt) if instr.rt else 0
      rs_val = instr.rs_val
      rt_val = instr.rt_val
      instr.stage = "ID"
      if op == "beq" and rs_val == rt_val:
          branch_taken = True
      elif op == "bne" and rs_val != rt_val:
          branch_taken = True
      elif op=="blt" and rs_val < rt_val:
          branch_taken = True
      elif op=="bgt" and rs_val > rt_val:
          branch_taken = True
      elif op=="ble" and rs_val <= rt_val:
          branch_taken = True
      elif op=="bge" and rs_val >= rt_val:
          branch_taken = True
      elif op in ["j","jal","jr"]:
          branch_taken = True
          if(op=="jal"):
              rf.write(31,pc+4)
      if branch_taken and imm in label_dict and op!="jr":
          new_pc = label_dict[imm]
          print(f"[BRANCH] Taken at PC=0x{instr.pc:08X}, jumping to 0x{new_pc:08X} (label: {imm})")
      if branch_taken and rs_val and op=="jr":
          new_pc = rs_val
          print(f"[BRANCH] Taken at PC=0x{instr.pc:08X}, jumping to 0x{new_pc:08X} (label: {imm})")
  return instr, branch_taken, new_pc


def EX(instr,rf, label_dict, fwd_rs, fwd_rt, fwd_enabled=True, ex_mem_instr=None, mem_wb_instr=None):

  if instr:
      instr.stage = "EX"
      op = instr.op

      # Get original values
      rs_val = getattr(instr, 'rs_val', 0)
      rt_val = getattr(instr, 'rt_val', 0)

      # Apply forwarding if enabled
      if fwd_enabled:
          if fwd_rs == "10" and ex_mem_instr and hasattr(ex_mem_instr, 'result'):
              rs_val = ex_mem_instr.result
              print(f"    [FWD] RS forwarded from EX/MEM: {rs_val}")
          elif fwd_rs == "01" and mem_wb_instr and hasattr(mem_wb_instr, 'result'):
              rs_val = mem_wb_instr.result
              print(f"    [FWD] RS forwarded from MEM/WB: {rs_val}")

          if fwd_rt == "10" and ex_mem_instr and hasattr(ex_mem_instr, 'result'):
              rt_val = ex_mem_instr.result
              print(f"    [FWD] RT forwarded from EX/MEM: {rt_val}")
          elif fwd_rt == "01" and mem_wb_instr and hasattr(mem_wb_instr, 'result'):
              rt_val = mem_wb_instr.result
              print(f"    [FWD] RT forwarded from MEM/WB: {rt_val}")

      imm = instr.imm

      if op in ["add", "sub", "and", "or", "slt"]:
          instr.result = {
              "add": rs_val + rt_val,
              "sub": rs_val - rt_val,
              "and": rs_val & rt_val,
              "or": rs_val | rt_val,
              "nor":~(rs_val | rt_val),
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
              print("Exception dont divide by zero")
      elif op in ["mfhi"]:
          instr.result = rf.Hi
      elif op in ["mflo"]:
          instr.result = rf.Lo
      elif op in ["addi", "andi", "ori", "slti"]:
          instr.result = {
              "addi": rs_val + imm,
              "andi": rs_val & imm,
              "ori": rs_val | imm,
              "slti": 1 if rs_val < imm else 0
          }[op]
      elif op in ["srl","sra","sll"]:
        if rs_val<0:
          print("SHAMT must be positive")
        else:
              instr.result={
                  "srl": (rs_val % 0x100000000) >> imm,
                    "sll": rs_val << imm,
                    "sra": rs_val >> imm
              }
  return instr


def MEM(instr, dmem):
  if instr:
      instr.stage = "MEM"
      if instr.op == "lw":
          instr.result = dmem.load(instr.result)
      elif instr.op == "sw":
          dmem.store(instr.result, instr.rt_val)
  return instr

def WB(instr, rf):
  if instr:
      instr.stage = "WB"
      # R-type instructions write to rd
      if instr.op in ["add", "sub", "and", "or", "slt","nor","mult","div","mfhi","mflo"]:
          if instr.rd:
              rf.write(instr.rd, instr.result)
              print(f"    [WB] Writing ${instr.rd} = {instr.result}")
      # I-type instructions write to rt
      elif instr.op in ["addi", "andi", "ori", "slti", "lw","srl","sll","sra"]:
          if instr.rt:
              rf.write(instr.rt, instr.result)
              print(f"    [WB] Writing ${instr.rt} = {instr.result}")



# ---------------------- SIMULATE ----------------------
STAGES = ["IF", "ID", "EX", "MEM", "WB"]

def simulate(imem, rf, dmem):
  pc = 0
  cycle = -1
  pipeline = {stage: None for stage in STAGES}
  instructions = imem.instructions
  label_dict = imem.label_dict
  stall_next_if = False
  while pc < len(instructions) * 4 or any(pipeline.values()) and cycle <1000:
      cycle += 1
      pipeline_str = ', '.join(f"{k}: {i.op if i else '---'}" for k, i in pipeline.items())
      print(f"\nCycle {cycle:02d} | Pipeline: {{ {pipeline_str} }}")

      # Determine forwarding needs
      ex_mem_instr = pipeline["MEM"]
      mem_wb_instr = pipeline["WB"]
      id_ex_instr = pipeline["EX"]

      # Check what registers are being written
      ex_mem_rd = None
      ex_mem_regwrite = False
      if ex_mem_instr:
          if ex_mem_instr.op in ["add", "sub", "and", "or", "slt"]:
              ex_mem_rd = ex_mem_instr.rd
              ex_mem_regwrite = True
          elif ex_mem_instr.op in ["addi", "andi", "ori", "slti", "lw"]:
              ex_mem_rd = ex_mem_instr.rt
              ex_mem_regwrite = True

      mem_wb_rd = None
      mem_wb_regwrite = False
      if mem_wb_instr:
          if mem_wb_instr.op in ["add", "sub", "and", "or", "slt"]:
              mem_wb_rd = mem_wb_instr.rd
              mem_wb_regwrite = True
          elif mem_wb_instr.op in ["addi", "andi", "ori", "slti", "lw"]:
              mem_wb_rd = mem_wb_instr.rt
              mem_wb_regwrite = True

      # Check forwarding for current EX instruction
      fwd_rs, fwd_rt = "00", "00"
      if id_ex_instr:
          fwd_rs, fwd_rt = check_fwd(
              ex_mem_rd, ex_mem_regwrite,
              mem_wb_rd, mem_wb_regwrite,
              id_ex_instr.rs, id_ex_instr.rt
          )

      # Execute pipeline stages
      # WB stage
      if pipeline["WB"]:
          WB(pipeline["WB"], rf)

      # MEM stage
      pipeline["WB"] = pipeline["MEM"]
      if pipeline["WB"]:
          pipeline["WB"] = MEM(pipeline["WB"], dmem)

      # EX stage
      pipeline["MEM"] = pipeline["EX"]
      if pipeline["MEM"]:
          ex_result = EX(
              pipeline["MEM"],rf, label_dict, fwd_rs, fwd_rt, True,
              ex_mem_instr, mem_wb_instr
          )
          pipeline["MEM"] = ex_result


      # ID stage
      pipeline["EX"] = pipeline["ID"]
      if pipeline["EX"]:
          pipeline["EX"],branch_taken,new_pc = ID(pipeline["EX"], rf,label_dict,pc)
          if branch_taken and new_pc is not None:
              pc = new_pc
              print("    [BRANCH] Pipeline fwd")
          if pipeline["EX"] and pipeline["EX"].op == "jr":
              stall_next_if = True  # Prevent wrong fetch after jr


      # IF stage
      pipeline["ID"] = pipeline["IF"]
      fetched = None
      branch_stall = 0
      if stall_next_if:
            pipeline["IF"] = None  # insert a bubble
            stall_next_if = False  # reset the stall trigger
      else:
            if pc < len(instructions) * 4:
                fetched, branch_stall = IF(pc, imem)
                pipeline["IF"] = fetched
            if fetched:
                pc += 4
            if branch_stall:
                stall_next_if = True  # trigger stall for the next cycle
            elif not fetched:
                  pipeline["IF"] = None

      print("  Registers:")
      for reg, val in rf.reg.items():
          if val != 0:
              reg_name = REG_NAME_MAP.get(reg, f"${reg}")
              print(f"{reg_name:>5}: 0x{(val & 0xFFFFFFFF):08X}")


      print("  Memory:")
      if dmem.memory:
          for addr, val in dmem.memory.items():
              print(f"    [0x{addr:08X}]: 0x{val:08X}")
      else:
          print("    (empty)")

  print(f"\nSimulation completed in {cycle} cycles")


# ---------------------- MAIN PROGRAM ----------------------
imem = InstructionMemory()
rf = RegisterFile()
dmem = DataMemory()

program = """
    addi $t0, $zero, 1
    addi $t1, $zero, 1
    beq  $t0, $t1, target
    addi $t2, $zero, 9
target:
    addi $t3, $zero, 42
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
total_instr=0
b_instr=0

simulate(imem, rf, dmem)

branch_frequency = b_instr / total_instr
stall_cpi_due_to_branches = branch_frequency  # Since branch penalty = 2
print(f"Total Instructions: {total_instr}")
print(f"Total Branches: {b_instr}")
print(f"Branch frequency: {branch_frequency:.2f}")
print(f"Pipeline Stall Cycles per Instruction due to Branches: {stall_cpi_due_to_branches:.2f}")
